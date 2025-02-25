import os
import json
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from interactions import (
    Client,
    ComponentContext,
    Intents,
    Poll,
    PollMedia,
    StringSelectMenu,
    listen,
    slash_command,
    SlashContext,
    slash_option,
    OptionType,
)
from interactions.api.events.discord import MessagePollVoteAdd
from interactions.api.events import (
    Component,
)  # Pour écouter les callbacks des composants

load_dotenv()
bot = Client(token=os.environ["BOT_TOKEN"], intents=Intents.DEFAULT)

POLL_OPTIONS_FILE = "poll_options.json"
ACTIVE_POLL_MESSAGE = None
AUTRES_THREAD_CREATED = (
    False  # Indique si le thread "Autres" a été créé pour le sondage actif
)


def load_poll_options():
    try:
        with open(POLL_OPTIONS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_poll_options(options):
    with open(POLL_OPTIONS_FILE, "w") as f:
        json.dump(options, f)


async def create_poll(
    allow_multiselect=True,
    question="A quoi voulez-vous jouer ce soir ?",
    duration=10,
    content="**Sondage du jour :**",
):
    """
    Crée un sondage en ajoutant toujours les options "Autres" et "Je ne joue pas".
    Renvoie le message envoyé ou None en cas d'erreur.
    """
    global AUTRES_THREAD_CREATED
    options = load_poll_options()
    # Ajoute systématiquement les options "Autres" et "Je ne joue pas"
    options += ["Autres", "Je ne joue pas"]
    if not options:
        print("Aucune option de sondage n'est définie, le sondage ne peut être créé.")
        return None
    # Création des réponses sous forme de PollMedia
    poll_answers = [PollMedia.create(text=opt) for opt in options]
    poll = Poll.create(
        question=question,
        duration=duration,
        allow_multiselect=allow_multiselect,
        answers=poll_answers,
    )
    try:
        poll_channel_id = int(os.environ["POLL_CHANNEL_ID"])
        channel = await bot.fetch_channel(poll_channel_id)
        msg = await channel.send(content=content, poll=poll)
        print("Sondage créé avec succès.")
        AUTRES_THREAD_CREATED = False  # Réinitialisation pour le nouveau sondage
        return msg
    except Exception as e:
        print(f"Erreur lors de l'envoi du sondage : {e}")
        return None


async def update_poll_if_needed():
    """
    Si un sondage actif existe et qu'aucun vote n'est placé sur une option autre que
    "Autres" et "Je ne joue pas", supprime le sondage et le recrée avec les options à jour.
    """
    global ACTIVE_POLL_MESSAGE
    if ACTIVE_POLL_MESSAGE is None:
        return

    try:
        poll = ACTIVE_POLL_MESSAGE.poll
        has_vote = False
        if poll.results is not None and hasattr(poll.results, "answer_counts"):
            for answer_count in poll.results.answer_counts:
                matching_answer = next(
                    (pa for pa in poll.answers if pa.answer_id == answer_count.id), None
                )
                if matching_answer:
                    if (
                        matching_answer.poll_media.text
                        not in ["Autres", "Je ne joue pas"]
                        and answer_count.count > 0
                    ):
                        has_vote = True
                        break

        if not has_vote:
            print(
                "Aucun vote n'a été placé sur une option personnalisée. Mise à jour du sondage."
            )
            await ACTIVE_POLL_MESSAGE.delete()
            ACTIVE_POLL_MESSAGE = await create_poll(
                allow_multiselect=poll.allow_multiselect,
                question=poll.question.text,
                duration=10,
                content="**Sondage mis à jour :**",
            )
    except Exception as e:
        print(f"Erreur lors de la mise à jour du sondage : {e}")


@slash_command(name="add_poll_option", description="Ajouter une option au sondage")
@slash_option(
    name="option_text",
    description="Texte de l'option",
    required=True,
    opt_type=OptionType.STRING,
)
async def add_poll_option(ctx: SlashContext, option_text: str):
    options = load_poll_options()
    options.append(option_text)
    save_poll_options(options)
    await ctx.send(f"L'option **{option_text}** a été ajoutée.", ephemeral=True)
    await update_poll_if_needed()


@slash_command(
    name="remove_poll_option",
    description="Supprimer une option du sondage via un menu de sélection",
)
async def remove_poll_option(ctx: SlashContext):
    options = load_poll_options()
    if not options:
        await ctx.send("Aucune option n'est disponible à supprimer.", ephemeral=True)
        return

    # Utilise directement la liste d'options en arguments positionnels
    menu = StringSelectMenu(
        *options,
        custom_id="remove_poll_option_menu",
        placeholder="Choisissez une option à supprimer",
        min_values=1,
        max_values=1,
    )
    await ctx.send(
        "Sélectionnez une option à supprimer :", components=menu, ephemeral=True
    )


@listen(Component)
async def on_component(event: Component):
    ctx = event.ctx
    if ctx.custom_id == "remove_poll_option_menu":
        # Récupère la ou les valeurs sélectionnées par l'utilisateur
        if not ctx.values:
            await ctx.send("Aucune option sélectionnée.", ephemeral=True)
            return

        selected = ctx.values[0]
        options = load_poll_options()
        if selected in options:
            options.remove(selected)
            save_poll_options(options)
            await ctx.send(f"L'option **{selected}** a été supprimée.", ephemeral=True)
            await update_poll_if_needed()
        else:
            await ctx.send("L'option sélectionnée n'existe pas.", ephemeral=True)


async def schedule_daily_poll():
    """
    Tâche de fond qui attend jusqu'à 10h, crée le sondage et recommence le lendemain.
    Le sondage est créé avec une durée de 10 heures.
    """
    global ACTIVE_POLL_MESSAGE
    try:
        poll_channel_id = int(os.environ["POLL_CHANNEL_ID"])
    except (KeyError, ValueError):
        print(
            "Erreur : la variable d'environnement POLL_CHANNEL_ID n'est pas définie ou invalide."
        )
        return

    while True:
        now = datetime.now()
        next_run = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        print(f"Prochain sondage dans {wait_seconds/3600:.2f} heures.")
        await asyncio.sleep(wait_seconds)
        ACTIVE_POLL_MESSAGE = await create_poll(allow_multiselect=True)
        await asyncio.sleep(60)


@listen()
async def on_message_poll_vote_add(event: MessagePollVoteAdd):
    """
    Lorsqu'un utilisateur vote, vérifie via l'attribut answer_id si l'option votée est "Autres".
    Si c'est le cas et que le thread correspondant n'a pas encore été créé, crée un thread sous le sondage.
    """
    global ACTIVE_POLL_MESSAGE, AUTRES_THREAD_CREATED

    user = await event.fetch_user()
    print(f"[LOG] Utilisateur votant : {user.username}")

    if ACTIVE_POLL_MESSAGE:
        print(f"[LOG] Sondage en cours : {ACTIVE_POLL_MESSAGE.poll.question.text}")
    else:
        print("[LOG] Aucun sondage actif.")
        return

    ans_id = event.answer_id
    print(f"[LOG] ID de la réponse votée : {ans_id}")

    matching_answer = next(
        (pa for pa in ACTIVE_POLL_MESSAGE.poll.answers if pa.answer_id == ans_id),
        None,
    )
    if matching_answer:
        print(f"[LOG] Option votée : {matching_answer.poll_media.text} (ID: {ans_id})")
    else:
        print(f"[LOG] Aucun matching pour l'ID de réponse : {ans_id}")
        return

    if matching_answer and matching_answer.poll_media.text == "Autres":
        print("[LOG] Option 'Autres' détectée.")
        if not AUTRES_THREAD_CREATED:
            try:
                print("[LOG] Tentative de création du thread 'Discussion - Autres'...")
                thread = await ACTIVE_POLL_MESSAGE.create_thread(
                    name="Discussion - Autres",
                    auto_archive_duration=60,  # durée d'archive automatique en minutes
                )
                print("[LOG] Thread 'Discussion - Autres' créé avec succès.")
                AUTRES_THREAD_CREATED = True
            except Exception as e:
                print(f"[LOG] Erreur lors de la création du thread : {e}")
        else:
            print("[LOG] Le thread 'Discussion - Autres' a déjà été créé.")


@listen()
async def on_ready():
    print("Bot prêt!")
    asyncio.create_task(schedule_daily_poll())


bot.start(os.environ["BOT_TOKEN"])
