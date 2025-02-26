from interactions.api.events.discord import MessagePollVoteAdd
from interactions.api.events import Component
from datetime import datetime, timedelta
from dotenv import load_dotenv
from interactions import (
    StringSelectMenu,
    SlashContext,
    OptionType,
    PollMedia,
    Intents,
    Client,
    Poll,
    slash_command,
    slash_option,
    listen,
)
import asyncio
import json
import os

load_dotenv()
bot = Client(token=os.environ["BOT_TOKEN"], intents=Intents.DEFAULT)

POLL_OPTIONS_FILE = "poll_options.json"
ACTIVE_POLL_MESSAGE = None
AUTRES_THREAD_CREATED = False
AUTRES_THREAD = None


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
    global ACTIVE_POLL_MESSAGE, AUTRES_THREAD_CREATED, AUTRES_THREAD
    options = load_poll_options()
    options += ["Autres", "Je ne joue pas"]
    if not options:
        print("Aucune option de sondage n'est définie, le sondage ne peut être créé.")
        return None
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
        ACTIVE_POLL_MESSAGE = msg  # Mettre à jour la variable avec le nouveau sondage
        AUTRES_THREAD_CREATED = False
        AUTRES_THREAD = None
        return msg
    except Exception as e:
        print(f"Erreur lors de l'envoi du sondage : {e}")
        return None


async def update_poll_if_no_votes():
    global ACTIVE_POLL_MESSAGE
    if ACTIVE_POLL_MESSAGE is None:
        return False
    try:
        current_poll_msg = await ACTIVE_POLL_MESSAGE.channel.fetch_message(
            ACTIVE_POLL_MESSAGE.id
        )
        await current_poll_msg.delete()
        print("Sondage précédent supprimé.")
        ACTIVE_POLL_MESSAGE = None 
        return True
    except Exception as e:
        print(f"Erreur lors de la suppression du sondage : {e}")
        ACTIVE_POLL_MESSAGE = None 
        return False


@slash_command(name="add_poll_option", description="Ajouter une option au sondage")
@slash_option(
    name="option_text",
    description="Texte de l'option",
    required=True,
    opt_type=OptionType.STRING,
)
async def add_poll_option(ctx: SlashContext, option_text: str):
    options = load_poll_options()
    if option_text in options:
        await ctx.send(f"L'option **{option_text}** existe déjà.", ephemeral=True)
        return
    options.append(option_text)
    save_poll_options(options)
    if await update_poll_if_no_votes():
        ACTIVE_POLL_MESSAGE = await create_poll()
    await ctx.send(f"L'option **{option_text}** a été ajoutée.", ephemeral=True)


@slash_command(
    name="remove_poll_option",
    description="Supprimer une option du sondage via un menu de sélection",
)
async def remove_poll_option(ctx: SlashContext):
    options = load_poll_options()
    if not options:
        await ctx.send("Aucune option n'est disponible à supprimer.", ephemeral=True)
        return
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
        if not ctx.values:
            await ctx.send("Aucune option sélectionnée.", ephemeral=True)
            return
        selected = ctx.values[0]
        options = load_poll_options()
        if selected in options:
            options.remove(selected)
            save_poll_options(options)
            if await update_poll_if_no_votes():
                ACTIVE_POLL_MESSAGE = await create_poll()
            await ctx.send(f"L'option **{selected}** a été supprimée.", ephemeral=True)
        else:
            await ctx.send("L'option sélectionnée n'existe pas.", ephemeral=True)


async def schedule_daily_poll():
    global ACTIVE_POLL_MESSAGE, AUTRES_THREAD_CREATED, AUTRES_THREAD
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
        if ACTIVE_POLL_MESSAGE is not None:
            try:
                await ACTIVE_POLL_MESSAGE.delete()
                print("Sondage précédent supprimé.")
                ACTIVE_POLL_MESSAGE = (
                    None  # Mettre à jour la variable après suppression
                )
            except Exception as e:
                print(f"Erreur lors de la suppression du sondage précédent : {e}")
        AUTRES_THREAD_CREATED = False
        AUTRES_THREAD = None
        ACTIVE_POLL_MESSAGE = await create_poll(allow_multiselect=True)
        await asyncio.sleep(60)


@listen()
async def on_message_poll_vote_add(event: MessagePollVoteAdd):
    global ACTIVE_POLL_MESSAGE, AUTRES_THREAD_CREATED, AUTRES_THREAD
    user = await event.fetch_user()
    print(f"Utilisateur votant : {user.username}")
    if ACTIVE_POLL_MESSAGE:
        print(f"Sondage en cours : {ACTIVE_POLL_MESSAGE.poll.question.text}")
    else:
        print("Aucun sondage actif.")
        return
    ans_id = event.answer_id
    print(f"ID de la réponse votée : {ans_id}")
    matching_answer = next(
        (pa for pa in ACTIVE_POLL_MESSAGE.poll.answers if pa.answer_id == ans_id), None
    )
    if matching_answer:
        print(f"Option votée : {matching_answer.poll_media.text} (ID: {ans_id})")
    else:
        print(f"Aucun matching pour l'ID de réponse : {ans_id}")
        return
    if matching_answer and matching_answer.poll_media.text == "Autres":
        print("Option 'Autres' détectée.")
        if not AUTRES_THREAD_CREATED:
            try:
                thread = await ACTIVE_POLL_MESSAGE.create_thread(
                    name="Discussion - Autres", auto_archive_duration=60
                )
                print("Thread 'Discussion - Autres' créé avec succès.")
                AUTRES_THREAD_CREATED = True
                AUTRES_THREAD = thread
            except Exception as e:
                print(f"Erreur lors de la création du thread : {e}")


@listen()
async def on_ready():
    global ACTIVE_POLL_MESSAGE
    print("Bot prêt!")
    if ACTIVE_POLL_MESSAGE is None:
        ACTIVE_POLL_MESSAGE = await create_poll(allow_multiselect=True)
    asyncio.create_task(schedule_daily_poll())


bot.start(os.environ["BOT_TOKEN"])
