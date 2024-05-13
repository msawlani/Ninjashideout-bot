import os
from twitchio.ext import commands, sounds, routines, pubsub, eventsub
from dotenv import load_dotenv
import pymongo
import requests
import asyncio
import random
import re
import time
from datetime import datetime
from better_profanity import profanity

load_dotenv()

client = pymongo.MongoClient(os.environ.get('DBCONNECTION'))
mydb =  client["Ninjashideout"]
collection = mydb['commands']
kunaiSystem = mydb["viewers"]
timed_messages_col = mydb["timedmessages"]
links_col = mydb['links']
bannedwords_col = mydb['bannedwords']

data = collection.find()

viewers = []
qotd = ["If you could only play games for the rest of your life, what game would you play?",
"What is the most horrible food combination you can think of?",
"If you had enough money to buy a company, which one would it be?",
"Which video game character would you want to be friends with?",
"What's your favorite game to play with friends?",
"If you could travel anywhere in the world, where would you go?",
"What's your favorite movie or TV show?",
"What's your favorite book?",
"What's your favorite type of music?",
"If you could have any superpower, what would it be?",
"What's your favorite hobby?",
"What's your favorite type of weather?",
"What's your favorite animal?",
"What's your favorite type of food?",
"What's your favorite video game genre?",
"What's your favorite game to play solo?",
"What's your favorite game to play with a group?",
"What's your favorite game to play with friends?",
"What's your favorite game to play with family?",
"What's your favorite game to play with your significant other?",
"What's your favorite game to play with your pet?",
"What's your favorite game to play with your siblings?",
"What's your favorite game to play with your cousins?",
"What's your favorite game to play with your friends?",
"What's your favorite childhood memory that you can recall?"]
delete_attempts = {}
bannedwords = ["cunt","nigger", "nigga", "niggers", "f4f", "fag", "faggot" , "rtard", "retarded", "retard", "fagg", "rape", "gay"]
links_pattern = re.compile(
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)
raffle_participants = []
raffle_running = False
raffle_name = None
death_counter = 0
start_time = 0
permit = []
active_duels = {}
strictmode = False
livealready = False


def censor_with_exceptions(text):
    words = text.split()
    if strictmode:
        censored_words = [
            profanity.censor(word) for word in words
        ]
    else:
        censored_words = [
            word if word not in bannedwords else "*" * len(word) for word in words
        ]
    return " ".join(censored_words)

def CheckUser(status, username):
    viewer = {"username": username, "kunai": 0, "watchtime": 0, "achievements": []}
    foundViewer = kunaiSystem.find_one({"username": username})

    if status == "Joined":
        if foundViewer:
            viewers.append(
                    foundViewer['username']
                )
            print(viewers)        
        else:
            viewers.append(username)
            kunaiSystem.insert_one(viewer)
            print(viewers)
    else:
        viewers.remove(username)
        print(viewers)

def watchtime_calculate(seconds):
    total_hours = seconds / 3600
    hours =  int(total_hours)
    minutes = int((total_hours % 1)*60)
    return hours, minutes

def symbol_spam(message):
    pattern = re.compile(r'[^\w\s]')
    symbols = pattern.findall(message.content)
    threshold = 50
    return len(symbols) > threshold

def emote_spam(message):
    emotes_str = message.tags.get('emotes', '')
    emote_positions = re.findall(r'\d+', emotes_str)
    emote_threshold = 50 # Adjust this value based on your needs
    return len(emote_positions) > emote_threshold

async def streamInfo():
    streams = await bot.fetch_streams(user_logins=["sinsofaninja"])
    for stream in streams:
        title = stream.title
        game = stream.game_name
    return title, game


async def check_achievement(user_id, achievement_name, message):
    user = kunaiSystem.find_one({"username": user_id})
    if user and achievement_name in user["achievements"]:
        return True  # User has completed the achievement
    await message.channel.send(f"{message.author.name} has completed the {achievement_name} achievement!")
    return False  # User has not completed the achievement

def watch_viewers_collection():
    pipeline = [{"$match": {"operationType": "insert"}}]
    change_stream = kunaiSystem.watch(pipeline)
    return change_stream

async def monitor_viewers_changes():
    change_stream = watch_viewers_collection()
    for change in change_stream:
        print("New viewer added:", change)
        # Reload all viewers here
        # This could involve fetching the updated list of viewers from the database
        # and updating your bot's state accordingly
        await reload_viewers()

async def reload_viewers():
    global data
    data = collection.find()


class DuelSystem:
    global active_duels
    def initiate_duel(challenger, challenged, kunais):
        duel_id = f"{challenged}"
        active_duels[duel_id] = {'challenger':challenger, 'challenged':challenged, 'kunais':kunais}
        kunaiSystem.update_one({'username':challenger}, {"$inc":{"kunai": -kunais}})
        return duel_id

    def accept_duel(duel_id):
        if duel_id in active_duels:
            duel = active_duels[duel_id]
            winner = random.choice([duel['challenger'], duel['challenged']])
            kunaiSystem.update_one({"username":winner}, {"$inc":{"kunai":duel['kunais']}})
            del active_duels[duel_id]
            return winner
        return None

    def deny_duel(duel_id):
        if duel_id in active_duels:
            duel = active_duels[duel_id]
            kunaiSystem.update_one({"username":duel['challenger']}, {"$inc":{"kunai":duel['kunais']}})
            del active_duels[duel_id]
            return True
        return False
class MyBot(commands.Bot):

    def __init__(self, token, prefix, initial_channels):
        super().__init__(token=token, prefix=prefix, initial_channels=initial_channels, heartbeat=30.0)
        self.esclient = eventsub.EventSubWSClient(self)

    async def event_message(self, message):
        # An event inside a cog!
        if message.echo:
            return
        global delete_attempts
        channel = bot.get_channel("sinsofaninja")
        token = os.getenv("TOKEN")
        user = message.author.name
        broadcaster = os.getenv("STREAMER_ID")

        kunaiSystem.update_one({"username": user}, {"$inc": {"messages": 1}})
        viewer = kunaiSystem.find_one({"username":user})

        if viewer["messages"] == 1:
            if not await check_achievement(user, "FirstMessage", message):
                print("achievement")
                # If not, mark the achievement as completed
                kunaiSystem.update_one(
                    {"username": user}, {"$push": {"achievements": "FirstMessage"}}
                )
        elif viewer["messages"] == 20:
            if not await check_achievement(user, "SimpleChatter", message):
                print("achievement")
                # If not, mark the achievement as completed
                kunaiSystem.update_one(
                    {"username": user}, {"$push": {"achievements": "SimpleChatter"}}
                )
        elif viewer["messages"] == 50:
            if not await check_achievement(user, "AdvancedChatter", message):
                print("achievement")
                # If not, mark the achievement as completed
                kunaiSystem.update_one(
                    {"username": user}, {"$push": {"achievements": "AdvancedChatter"}}
                )

        print(message.content)
        message_id = message.id

        print(user)

        if (not message.author.is_mod or not message.author.is_broadcaster) and not user.name in permit:
            censored_text = censor_with_exceptions(message.content)

            if symbol_spam(message):
                # if user.name not in delete_attempts:
                #     delete_attempts[user.name] = 0
                await self._http.delete_chat_messages(
                    token, broadcaster, "584386199", message_id
                )
                await channel.send("Hey! Stop spamming symbols!")
                # delete_attempts[user.name] += 1

            if links_pattern.search(message.content):
                # if user.name not in delete_attempts:
                #     delete_attempts[user.name] = 0
                await self._http.delete_chat_messages(
                    token, broadcaster, "584386199", message_id
                )
                await channel.send("Your not allowed to post any links!")
                # delete_attempts[user.name] += 1

            if emote_spam(message):
                # if user.name not in delete_attempts:
                #     delete_attempts[user.name] = 0
                await self._http.delete_chat_messages(
                    token, broadcaster, "584386199", message_id
                )
                await channel.send("Hey! Stop spamming emotes!")

            # if user.name not in delete_attempts:
            #     delete_attempts[user.name] = 0
            if censored_text != message.content:
                await self._http.delete_chat_messages(
                    token, broadcaster, "584386199", message_id
                )
                await channel.send("Your message contains forbidden words!")
            # delete_attempts[user.name] += 1

            # if delete_attempts[user.name] >= 3:
            #     print("timing you out")
            #     await self._http.post_ban_timeout_user(token, broadcaster, "584386199", user.name, "I have told you many times to stop posting that! Now I have timed you out for a 3 minutes.", 60)
            #     delete_attempts[user.name] = 0

        await self.handle_commands(message)

    async def event_ready(self):
        print(f'Logged into Twitch | {self.nick}')
        global start_time
        self.water_reminder.start()
        self.break_reminder.start()
        self.follow_reminder.start()
        start_time = time.time()

    async def event_command_error(self, context: commands.Context, error: Exception):
        if isinstance(error, commands.CommandNotFound):
            return

        elif isinstance(error, commands.ArgumentParsingFailed):
            await context.send(error.message)

        elif isinstance(error, commands.MissingRequiredArgument):
            await context.send("Please include the following after the !commandname " + error.name)

        elif isinstance(
            error, commands.CheckFailure
        ):  # we'll explain checks later, but lets include it for now.
            await context.send("Sorry, you cant run that command: " + error.args[0])

        else:
            print(error)

    @routines.routine(minutes=20, wait_first=True)
    async def follow_reminder(self):
        channel = self.get_channel("sinsofaninja")
        await channel.send("If your enjoying the stream don't forget to hit follow and turn on notifications!")

    @routines.routine(minutes=30, wait_first=True)
    async def water_reminder(self):
        channel = bot.get_channel("sinsofaninja")
        await channel.send("Don't forget to drink water!")

    @routines.routine(minutes=60, wait_first=True)
    async def break_reminder(self):
        channel = bot.get_channel("sinsofaninja")
        await channel.send("sinsofaninja, Its time to take a short break to stretch and refill the water!")

    async def sub(self):
        token = os.getenv("TOKEN")
        broadcaster = os.getenv("STREAMER_ID")
        await self.esclient.subscribe_channel_update(
            broadcaster=broadcaster, token=token
        )
        await self.esclient.subscribe_channel_stream_start(
            broadcaster=broadcaster, token=token
        )
        await self.esclient.subscribe_channel_stream_end(
            broadcaster=broadcaster, token=token
        )
        await self.esclient.subscribe_channel_raid(token=token, from_broadcaster=broadcaster)
        await self.esclient.subscribe_channel_follows_v2(
            broadcaster=broadcaster, moderator="584386199", token=token
        )
        await self.esclient.subscribe_channel_shoutout_create(
            broadcaster=broadcaster, moderator="584386199", token=token
        )

bot = MyBot(
    token=os.environ.get("TMI_TOKEN"),
    prefix="!",
    initial_channels=[os.environ.get("CHANNEL")],
)

bot.loop.create_task(bot.sub())
# bot.loop.create_task(monitor_viewers_changes())

for doc in data:
    @bot.command(name=doc['command'])
    @commands.cooldown(rate=1, per=30, bucket=commands.Bucket.channel)
    async def command_func(ctx: commands.Context) -> None:
        response = collection.find_one({"command": ctx.command.name})
        await ctx.send(response['message'])

@routines.routine(seconds=1)
async def WatchTime():
    for viewer in viewers:
        kunaiSystem.update_one({"username": viewer}, {"$inc": {"watchtime": 1}})

@routines.routine(minutes=6)
async def PointSystem():
    for viewer in viewers:
        kunaiSystem.update_one({"username": viewer}, {"$inc": {"kunai": 1}})        

@bot.command(name='duels')
async def duel(ctx: commands.Context):
    global duels
    # Check if the user has enough points to wager
    # This is a placeholder. Replace with your logic to check the user's points.
    await ctx.send(f'Current duels are as followed: {duels}')

@bot.command(name='strictmode')
async def filterstrict(ctx: commands.Context):
    if ctx.author.is_mod or ctx.author.is_broadcaster:
        global strictmode
        strictmode = not strictmode
        if strictmode == True:
            await ctx.send('Strict mode enabled!')
            return
        await ctx.send('Strict mode disabled!')

@bot.command(name="duel")
async def duel(ctx: commands.Context, user: str, kunai: int):
    duel_id = DuelSystem.initiate_duel(ctx.author.name, user, kunai)
    await ctx.send(f'{user}, {ctx.author.name} has challenged you to a duel for {kunai} kunais. Type !accept to accept the challenge or !deny to decline. Its your choice!')

@bot.command(name='accept')
async def accept(ctx: commands.Context):
    winner = DuelSystem.accept_duel(ctx.author.name)
    if winner:
        await  ctx.send(f'{winner} has won the duel!')
    else:
        await  ctx.send('There is no active duel for you.')

@bot.command(name='deny')
async def deny(ctx: commands.Context,):
    if DuelSystem.deny_duel(ctx.author.name):
        await ctx.send(f'{ctx.author.name}, you have denied the duel!')
    else:
        await ctx.send('There is no active duel for you.')

@bot.command(name="uptime")
@commands.cooldown(rate=1, per=30, bucket=commands.Bucket.channel)
async def uptime(ctx: commands.Context):
    global start_time
    current_time = time.time()
    difference = current_time - start_time
    uptime = str(datetime.timedelta(seconds=int(round(difference))))
    await ctx.send(f"Uptime: {uptime}")

@bot.command(name="qotd")
async def qotd_command(ctx: commands.Context):
    today = datetime.now().date()
    question_index = today.day % len(qotd)
    question = qotd[question_index]
    await ctx.send(f"Question of the day: {question}")

@bot.command(name="livealready")
async def live_already(ctx: commands.Context):
    if ctx.author.is_mod or ctx.author.is_broadcaster:
        global live_already
        live_already = True
        await ctx.send("Point system and watch time is now active!")
        if live_already:
            WatchTime.start()
            PointSystem.start()

@bot.command(name="startraffle")
async def raffle_cmd(ctx: commands.Context, title: str, time: int) -> None:
    global raffle_running
    global raffle_name
    if ctx.author.is_mod:
        if raffle_running:
            await ctx.send("A raffle is already running.")
            return

        raffle_running = True
        raffle_name = title
        await ctx.send(f"{raffle_name} Raffle has started! Type !join to join the raffle.")
        print(raffle_name)
        
        reminder_routine.start(ctx)
        
        await asyncio.sleep(60 * time)
        if not raffle_participants:
            await  ctx.send("No one joined the raffle. Raffle cancelled.")
            raffle_running = False
            return

        winner = random.choice(list(raffle_participants))
        await ctx.send(f"The winner of the raffle is {winner}! Congratulations!")
        raffle_name = None
        raffle_participants.clear()
        raffle_running = False

@routines.routine(seconds=30, iterations=5)
async def reminder_routine(ctx):
    await ctx.send(
        f"The {raffle_name} raffle is currently active !join to join the raffle!"
    )

@bot.command(name="join", aliases=("JOIN", "Join"))
async def join_command(ctx: commands.Context):
    if not raffle_name == "kunai":
        return
    
    if not ctx.author.name in raffle_participants:
        raffle_participants.append(ctx.author.name)

@bot.command(name="giveaway", aliases=("Giveaway", "GIVEAWAY"))
async def join_command(ctx: commands.Context):
        if not raffle_name == "giveaway":
            return
        
        if not ctx.author.name in raffle_participants:
            raffle_participants.append(ctx.author.name)

@bot.command(name="streaminfo")
@commands.cooldown(rate=1, per=30, bucket=commands.Bucket.channel)
async def stream_info(ctx: commands.Context):
    title, game = await streamInfo()
    await ctx.send(f"Title of the stream is: {title} and the current game we are playing is {game}")

@bot.command(name="newfeature")
async def new_features(ctx: commands.Context):
    await ctx.channel.send(f"You can now earn achievements in chat. This is a new feature and is in testing! so far there are only achievements for chatting but more will come soon!")

@bot.command(name="achievements")
async def achievements(ctx: commands.Context):
    user = kunaiSystem.find_one({'username': ctx.author.name})
    achievements_message = ', '.join(user['achievements'])
    await ctx.channel.send(f"{ctx.author.name} you have completed the following achievements: {achievements_message}")

@bot.command(name="so")
async def shoutout(ctx: commands.Context, user: str):
    if ctx.author.is_broadcaster or ctx.author.is_mod:
        await ctx.send(
            f"Go follow this amazing person! https://twitch.tv/{user}"
        )


# @bot.command(name="quote")
# @commands.cooldown(rate=1, per=30, bucket=commands.Bucket.channel)
# async def stream_info(ctx: commands.Context, quote_num: int):


# @bot.command(name="addcomm")
# async def addCommand(ctx: commands.Context, command: str, message: str):
#     collection.insert_one({"command": command, "message": message})
#     await ctx.send(f"Added command '{command}'.")


# @bot.command(name="deletecomm")
# async def deleteCommand(ctx: commands.Context, command: str):
#     collection.delete_one({"command": command})
#     await ctx.send(f"Deleted command '{command}'")


@bot.command(name="slots")
# @commands.cooldown(rate=1, per=30, bucket=commands.Bucket.channel)
async def slots(ctx: commands.Context, amount: int):
    foundviewerkunai = kunaiSystem.find_one({"username": ctx.author.name})
    currentkunai = foundviewerkunai["kunai"]
    if currentkunai > 0:
        if currentkunai - amount < 0:
            kunaiSystem.update_one(
                {"username": ctx.author.name},
                {"$inc": {"kunai": -currentkunai}},
            )
            symbols = ['🍇', '🍊', '🍋', '🍒', '🔔', '🍀']
            spin_results = [random.choice(symbols) for _ in range(3)]

            # Determine the outcome
            if spin_results[0] == spin_results[1] == spin_results[2]:  # All symbols match
                won = currentkunai * 2
                outcome = f"You won! {won} kunai(s) Congratulations!"
                kunaiSystem.update_one({"username": ctx.author.name}, {"$inc": {"kunai": won}})
            else:
                outcome = "No match. Better luck next time!"

            # Send the spin results and outcome to the chat
            await ctx.send(f"{ctx.author.name} spun: {spin_results[0]}, {spin_results[1]}, {spin_results[2]}. {outcome}")
        else:
            kunaiSystem.update_one(
                {"username": ctx.author.name},
                {"$inc": {"kunai": -amount}},
            )
            symbols = ['🍇', '🍊', '🍋', '🍒', '🔔', '🍀']
            spin_results = [random.choice(symbols) for _ in range(3)]

            # Determine the outcome
            if spin_results[0] == spin_results[1] == spin_results[2]:  # All symbols match
                won = amount * 2
                outcome = f"You won! {won} kunai(s) Congratulations!"
                kunaiSystem.update_one({"username": ctx.author.name}, {"$inc": {"kunai": won}})
            else:
                outcome = "No match. Better luck next time!"

            # Send the spin results and outcome to the chat
            await ctx.send(f"{ctx.author.name} spun: {spin_results[0]}, {spin_results[1]}, {spin_results[2]}. {outcome}")
    else:
        await ctx.send("You don't have any kunai!")

@bot.command(name="permit")
async def permit_Command(ctx: commands.Context, user: str):
    if ctx.author.is_mod:
        permit.append(user)
        print(permit)
        await asyncio.sleep(60)
        permit.remove(user)
        print(permit) 

@bot.command(name="watchtime")
@commands.cooldown(rate=1, per=30, bucket=commands.Bucket.channel)
async def watchtime(ctx: commands.Context):
    seconds = kunaiSystem.find_one({"username": ctx.author.name})['watchtime']
    hours, minutes = watchtime_calculate(seconds)
    await ctx.send(f"{ctx.author.name}, you have watch the steam for {hours}.{minutes} hours!")

@bot.command(name="death", aliases=("DEATH", "Death"))
async def deathCounter(ctx: commands.Context):
    if ctx.author.is_mod:
        global death_counter
        death_counter += 1
        await ctx.send(f"sinsofaninja, has died {death_counter} times") 

@bot.command(name="deaths", aliases=("Deaths", "DEATHS"))
@commands.cooldown(rate=1, per=30, bucket=commands.Bucket.channel)
async def Deaths(ctx: commands.Context):
    await ctx.send(f"sinsofaninja has {death_counter} deaths.")

@bot.command(name="welcome", aliases=("WELCOME", "Welcome"))
@commands.cooldown(rate=1, per=30, bucket=commands.Bucket.channel)
async  def welcomeMessage(ctx: commands.Context):
    await ctx.send("Welcome to the stream where we talk about games, food, music and stuff!")

@bot.command(name="add")
async def give_kunai(ctx: commands.Context, amount: int, user: str ) -> None:
    if ctx.author.is_mod:
        if user == "all":
            for viewer in viewers:
                kunaiSystem.update_one({"username": viewer}, {"$inc": {"kunai": amount}})
        else:
            foundviewerkunai = kunaiSystem.find_one({"username": user})
            currentkunai = foundviewerkunai["kunai"]

            if currentkunai + amount > 0:
                kunaiSystem.update_one(
                    {"username": user}, {"$inc": {"kunai": amount}}
                )
                await ctx.send(
                    f"Added {amount} kunai(s) to {user}. They now have {foundviewerkunai['kunai']}."
                )

@bot.command(name="remove")
async def Remove_kunai(ctx: commands.Context, amount: int, user: str ) -> None:
    if ctx.author.is_mod:        
        foundviewerkunai = kunaiSystem.find_one({"username": user})
        currentkunai = foundviewerkunai["kunai"]

        if currentkunai - amount < 0:
            kunaiSystem.update_one(
                {"username": user},
                {"$inc": {"kunai": -currentkunai}},
            )
            foundviewer = kunaiSystem.find_one({"username": user})
            await ctx.send(
                f"Removed {amount} kunai(s) from {user}. They now have {foundviewer['kunai']}."
            )
        else:
            kunaiSystem.update_one(
                {"username": user},
                {"$inc": {"kunai": -amount}},
            )
            foundviewer = kunaiSystem.find_one({"username": user})
            await ctx.send(
                f"Removed {amount} kunai(s) from {user}. They now have {foundviewer['kunai']}."
            )


@bot.command(name="currency", aliases=("kunai?"))
@commands.cooldown(rate=1, per=30, bucket=commands.Bucket.channel)
async def kunai_help_command(ctx: commands.Context):
    await ctx.send("Everyone is earning kunais while they watch the stream. Currently its 1 every 6 minutes. You can use the kunais to play the slot machine. Will be adding more options in the future.")

@bot.command(name="kunai")
async def show_kunai(ctx: commands.Context):
    foundviewerkunai = kunaiSystem.find_one({"username": ctx.author.name})
    currentkunai = foundviewerkunai["kunai"]
    if currentkunai - 1 < 0:
        await ctx.send(f"{ctx.author.name}, You have {currentkunai} kunai(s).")
    else:    
        kunaiSystem.update_one(
            {"username": ctx.author.name}, {"$inc": {"kunai": -1}}
        )
        foundviewer = kunaiSystem.find_one({"username": ctx.author.name})
        await ctx.send(f"{ctx.author.name}, You have {foundviewer['kunai']} kunai(s).")

@bot.command(name="check")
async def check_kunai(ctx: commands.Context, user: str):
    if ctx.author.is_broadcaster or ctx.author.is_mod:
        foundviewer = kunaiSystem.find_one({"username": user})
        await ctx.send(f"{user}, You have {foundviewer['kunai']} kunai(s).")


@bot.command(name="song")
@commands.cooldown(rate=1, per=30, bucket=commands.Bucket.channel)
async def song(ctx: commands.Context):
    try:
        response = requests.get(
            "https://groke.se/twitch/spotify/?9f7081b35b86f448e452bc81935f2927"
        )

        data = response.text

        await ctx.send(f"{ctx.author.name}, We are currently listening to {data}")

    except Exception as error:
        print(f"Error: {error}")

@bot.command(name="followed", aliases=("Followed", "FOLLOWED"))
@commands.cooldown(rate=1, per=30, bucket=commands.Bucket.channel)
async def followed(ctx: commands.Context):
    try:
        response = requests.get(
            f"https://decapi.me/twitch/followed/sinsofaninja/{ctx.author.name}?token=CpuAgUaMy7kOb9vJhHsCoxSbb54FMd20rGb3PUgI"
        )

        data = response.text

        await ctx.send(f"{ctx.author.name}, has been following since {data}")

    except Exception as error:
        print(f"Error: {error}")


@bot.command(name="highlight", aliases=("lh", "HightLight", "Highlight", "HIGHLIGHT"))
@commands.cooldown(rate=1, per=30, bucket=commands.Bucket.channel)
async def highlight(ctx: commands.Context):
    try:
        response = requests.get(f"https://decapi.me/twitch/highlight/sinsofaninja")

        data = response.text

        await ctx.send(f"Here is my latest highlight: {data}")

    except Exception as error:
        print(f"Error: {error}")


@bot.command(name="playlist")
async def playlist_command(ctx: commands.Context):
    await ctx.send(
        f"Link to my playlist: https://open.spotify.com/playlist/7qcD6fSV5g5QunS0qVbRcQ?si=75732ca1e8b445c1"
    )

@bot.command(name="recthat")
async def record_that(ctx: commands.Context):
    try:
        id = os.getenv("STREAMER_ID")
        headers = {
            "Client-ID": os.getenv("STREAMER_CLIENT_ID"),
            "Authorization": os.getenv("STREAMER_OAUTH2"),
        }
        response = requests.post(
            f"https://api.twitch.tv/helix/clips?broadcaster_id={id}",
            headers=headers,
        )

        data = response.json()

        if response.ok:
            await ctx.send(f"Moment has successfully been captured! {data['message']}")
        else:
            await ctx.send(f"Moment could not be captured! {data['message']}")
    except Exception as error:
        print(f"Error: {error}")


@bot.event()
async def event_error(error, data):
    print(f"Error occurred: {error}")
    print(f"Data: {data}")

@bot.event()
async def event_eventsub_notification_channel_shoutout_create(payload: eventsub.ChannelShoutoutCreateData):
    channel = bot.get_channel("sinsofaninja")
    await channel.send(f"Go check this amazing person out {payload.data.to_broadcaster}")


@bot.event()
async def event_eventsub_notification_raid(event: eventsub.ChannelRaidData):
    # Correctly access the raider's name
    raider_name = event.data.raider.display_name

    # Get the channel object for your chat
    channel = bot.get_channel("your_chat_channel_name")

    # Send a message to your chat
    await channel.send(f"Starting a raid by {raider_name}")

@bot.event()
async def event_command_error(ctx: commands.Context, error):
    retry_after = error.retry_after
    await ctx.send(f"{ctx.command.name} command is on cooldown try again in {retry_after:.2f} seconds")

@bot.event()
async def event_eventsub_notification_stream_start(payload: eventsub.StreamOnlineData
    ) -> None:
    print("Received event!")
    channel = bot.get_channel("sinsofaninja")
    title, game = await streamInfo()
    WatchTime.start()
    PointSystem.start()
    await channel.send(f"{payload.data.broadcaster.name} has started streaming with title: {title} playing {game}! Everyone has started earning kuanis.")


@bot.event()
async def event_eventsub_notification_stream_end(
    payload: eventsub.StreamOfflineData,
) -> None:
    print("Received event!")
    channel = bot.get_channel("sinsofaninja")
    await channel.send(f"{payload.data.broadcaster.name}'s stream has ended! Thank you to everyone tuning in today!")

@bot.event()
async def event_eventsub_notification_followV2(payload: eventsub.ChannelFollowData
    ) -> None:
    print("Received event!")
    channel = bot.get_channel("sinsofaninja")
    await channel.send(f"Thank you {payload.data.user.name} for following the channel! Welcome to the community!")

@bot.event()
async def event_eventsub_notification_channel_update(payload: eventsub.ChannelUpdateData
) -> None:
    print("Received event!")
    channel = bot.get_channel("sinsofaninja")
    await channel.send(f"Stream title has been updated to: {payload.data.title} and category is now {payload.data.category_name}")

@bot.event()
async def event_join(channel, user):
    CheckUser("Joined", user.name)

@bot.event()
async def event_left(channel, user):
    CheckUser("Left", user.name)

if __name__ == "__main__":
    bot.run()
