import discord
from discord import app_commands
from discord.ext import commands
import pymongo
from datetime import datetime
import pytz
from PIL import Image, ImageDraw, ImageFont
import os
import random
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
MONGODB_URI = os.getenv('MONGODB_URI')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Connect to MongoDB
mongo_client = pymongo.MongoClient(MONGODB_URI)

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Utility functions
def get_timestamp(dd, mm, yyyy, hour, minute, ampm=None):
    try:
        hour = int(hour) % 12 + (12 if ampm and ampm.lower() == 'pm' else 0)
        dt = datetime(int(yyyy), int(mm), int(dd), int(hour), int(minute), tzinfo=pytz.UTC)
        return int(dt.timestamp())
    except ValueError:
        return None

def create_tournament_image(team1, team2, time_str, logo_path, thumbnail_path):
    bg_files = ['images/bg1.jpg', 'images/bg2.jpg', 'images/bg3.jpg']
    base_image = Image.open(random.choice(bg_files)).convert('RGBA').resize((800, 600))
    draw = ImageDraw.Draw(base_image)
    font = ImageFont.truetype('fonts/arial.ttf', 40)

    if logo_path and os.path.exists(logo_path):
        logo = Image.open(logo_path).convert('RGBA').resize((200, 100))
        base_image.paste(logo, (300, 20), logo)

    vs_text = f"{team1} VS {team2}"
    draw.text((base_image.width // 2 - 100, base_image.height // 2), vs_text, fill='white', font=font)

    draw.text((50, base_image.height - 50), time_str, fill='white', font=font)

    if thumbnail_path and os.path.exists(thumbnail_path):
        thumbnail = Image.open(thumbnail_path).convert('RGBA').resize((100, 100))
        base_image.paste(thumbnail, (base_image.width - 120, base_image.height - 120), thumbnail)

    output_path = 'images/output.png'
    base_image.save(output_path)
    return output_path

# Bot ready event
@bot.event
async def on_ready():
    print(f'Bot {bot.user} is ready!')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'Error syncing commands: {e}')

# Autocomplete for event titles
async def event_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    tour_name = interaction.guild.name.replace(" ", "_").lower()
    db = mongo_client[tour_name]
    events = db['events'].find()
    return [
        app_commands.Choice(name=event['title'], value=event['title'])
        for event in events if current.lower() in event['title'].lower()
    ][:25]

# Tournament command group
@app_commands.guild_only()
class TournamentCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="tournament", description="Manage tournaments")

tournament = TournamentCommands()
bot.tree.add_command(tournament)

# /config set
@tournament.command(name="config_set", description="Set tournament configuration")
@app_commands.describe(
    bot_op_role="Role that manages bot events",
    judge_role="Judge role",
    recorder_role="Recorder role",
    schedule_channel="Channel for schedules",
    results_channel="Channel for results",
    notification_channel="Channel for notifications",
    transcript_channel="Channel for activity logs",
    thumbnail_channel="Channel for thumbnails",
    tour_logo="Tournament logo URL"
)
async def config_set(
    interaction: discord.Interaction,
    bot_op_role: discord.Role,
    judge_role: discord.Role,
    recorder_role: discord.Role,
    schedule_channel: discord.TextChannel,
    results_channel: discord.TextChannel,
    notification_channel: discord.TextChannel,
    transcript_channel: discord.TextChannel,
    thumbnail_channel: discord.TextChannel,
    tour_logo: str
):
    if not any(role.id == bot_op_role.id for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission!", ephemeral=True)
        return

    tour_name = interaction.guild.name.replace(" ", "_").lower()
    db = mongo_client[tour_name]
    config_collection = db['config']
    config_data = {
        'guild_id': interaction.guild.id,
        'bot_op_role': bot_op_role.id,
        'judge_role': judge_role.id,
        'recorder_role': recorder_role.id,
        'schedule_channel': schedule_channel.id,
        'results_channel': results_channel.id,
        'notification_channel': notification_channel.id,
        'transcript_channel': transcript_channel.id,
        'thumbnail_channel': thumbnail_channel.id,
        'tour_logo': tour_logo
    }
    config_collection.update_one({'guild_id': interaction.guild.id}, {'$set': config_data}, upsert=True)

    await log_action(db, interaction, f"Config set by {interaction.user.mention}")
    await interaction.response.send_message("Configuration set successfully!", ephemeral=True)

# /config edit
@tournament.command(name="config_edit", description="Edit tournament configuration")
@app_commands.describe(
    bot_op_role="Role that manages bot events",
    judge_role="Judge role",
    recorder_role="Recorder role",
    schedule_channel="Channel for schedules",
    results_channel="Channel for results",
    notification_channel="Channel for notifications",
    transcript_channel="Channel for activity logs",
    thumbnail_channel="Channel for thumbnails",
    tour_logo="Tournament logo URL"
)
async def config_edit(
    interaction: discord.Interaction,
    bot_op_role: discord.Role = None,
    judge_role: discord.Role = None,
    recorder_role: discord.Role = None,
    schedule_channel: discord.TextChannel = None,
    results_channel: discord.TextChannel = None,
    notification_channel: discord.TextChannel = None,
    transcript_channel: discord.TextChannel = None,
    thumbnail_channel: discord.TextChannel = None,
    tour_logo: str = None
):
    tour_name = interaction.guild.name.replace(" ", "_").lower()
    db = mongo_client[tour_name]
    config = db['config'].find_one({'guild_id': interaction.guild.id})

    if not config or not any(role.id == config['bot_op_role'] for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission!", ephemeral=True)
        return

    update_data = {}
    if bot_op_role:
        update_data['bot_op_role'] = bot_op_role.id
    if judge_role:
        update_data['judge_role'] = judge_role.id
    if recorder_role:
        update_data['recorder_role'] = recorder_role.id
    if schedule_channel:
        update_data['schedule_channel'] = schedule_channel.id
    if results_channel:
        update_data['results_channel'] = results_channel.id
    if notification_channel:
        update_data['notification_channel'] = notification_channel.id
    if transcript_channel:
        update_data['transcript_channel'] = transcript_channel.id
    if thumbnail_channel:
        update_data['thumbnail_channel'] = thumbnail_channel.id
    if tour_logo:
        update_data['tour_logo'] = tour_logo

    if update_data:
        db['config'].update_one({'guild_id': interaction.guild.id}, {'$set': update_data})
        await log_action(db, interaction, f"Config edited by {interaction.user.mention}")
        await interaction.response.send_message("Configuration updated!", ephemeral=True)
    else:
        await interaction.response.send_message("Please specify at least one field to edit!", ephemeral=True)

# /send_regis
@tournament.command(name="send_regis", description="Register for a tournament")
@app_commands.describe(
    channel="Channel to send registration",
    data="Tournament data",
    embedded_image="Embedded image URL"
)
async def send_regis(interaction: discord.Interaction, channel: discord.TextChannel, data: str, embedded_image: str = None):
    tour_name = interaction.guild.name.replace(" ", "_").lower()
    db = mongo_client[tour_name]
    config = db['config'].find_one({'guild_id': interaction.guild.id})
    if not config:
        await interaction.response.send_message("Config not set! Use /config_set first.", ephemeral=True)
        return

    embed = discord.Embed(title="Tournament Registration", description=data, color=discord.Color.green())
    if embedded_image:
        embed.set_image(url=embedded_image)
    embed.add_field(name="Discord Username", value=interaction.user.mention, inline=False)
    embed.add_field(name="Game ID", value="Pending input", inline=False)

    class RegistrationForm(discord.ui.Modal, title="Enter Game ID"):
        game_id = discord.ui.TextInput(label="Game ID", placeholder="e.g., 25CDF5286DC38DAD")

        async def on_submit(self, interaction: discord.Interaction):
            regis_channel = bot.get_channel(88685575446)
            if not regis_channel:
                await interaction.response.send_message("Registration channel not found!", ephemeral=True)
                return

            embed.set_field_at(1, name="Game ID", value=self.game_id.value, inline=False)
            await regis_channel.send(embed=embed)
            db['registrations'].insert_one({
                'user_id': interaction.user.id,
                'username': interaction.user.name,
                'game_id': self.game_id.value,
                'timestamp': datetime.utcnow()
            })
            await log_action(db, interaction, f"Registration by {interaction.user.mention} with Game ID: {self.game_id.value}")
            await interaction.response.send_message("Registration submitted!", ephemeral=True)

    await interaction.response.send_modal(RegistrationForm())

# /staff_data
@tournament.command(name="staff_data", description="Submit staff data")
@app_commands.describe(
    game_name="Game name",
    game_id="Game ID",
    discord_username="Discord username",
    discord_tag="Discord tag",
    discord_id="Discord ID"
)
async def staff_data(
    interaction: discord.Interaction,
    game_name: str,
    game_id: str,
    discord_username: str,
    discord_tag: str,
    discord_id: str
):
    tour_name = interaction.guild.name.replace(" ", "_").lower()
    db = mongo_client[tour_name]
    config = db['config'].find_one({'guild_id': interaction.guild.id})
    if not config:
        await interaction.response.send_message("Config not set! Use /config_set first.", ephemeral=True)
        return

    staff_channel = bot.get_channel(57465465)
    if not staff_channel:
        await interaction.response.send_message("Staff channel not found!", ephemeral=True)
        return

    embed = discord.Embed(title="Staff Data", color=discord.Color.blue())
    embed.add_field(name="Game Name", value=game_name, inline=False)
    embed.add_field(name="Game ID", value=game_id, inline=False)
    embed.add_field(name="Discord Username", value=discord_username, inline=False)
    embed.add_field(name="Discord Tag", value=discord_tag, inline=False)
    embed.add_field(name="Discord ID", value=discord_id, inline=False)

    await staff_channel.send(embed=embed)
    db['staff'].insert_one({
        'game_name': game_name,
        'game_id': game_id,
        'discord_username': discord_username,
        'discord_tag': discord_tag,
        'discord_id': discord_id,
        'timestamp': datetime.utcnow()
    })
    await log_action(db, interaction, f"Staff data submitted by {interaction.user.mention}")
    await interaction.response.send_message("Staff data submitted!", ephemeral=True)

# /staff_work
@tournament.command(name="staff_work", description="Show events judged by a staff member")
@app_commands.describe(staff="Staff member to check")
async def staff_work(interaction: discord.Interaction, staff: discord.User):
    tour_name = interaction.guild.name.replace(" ", "_").lower()
    db = mongo_client[tour_name]
    config = db['config'].find_one({'guild_id': interaction.guild.id})
    if not config:
        await interaction.response.send_message("Config not set! Use /config_set first.", ephemeral=True)
        return

    events = db['events'].find({'judge_id': staff.id})
    event_list = [
        f"- {event['title']} ({datetime.fromtimestamp(event['timestamp']).strftime('%d/%m/%Y')})"
        for event in events
    ]
    total_events = len(event_list)

    embed = discord.Embed(
        title=f"Judge Work for {staff.name}",
        description=f"Total Events Judged: {total_events}\n\n" + "\n".join(event_list) if event_list else "No events judged.",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await log_action(db, interaction, f"Viewed work history for {staff.mention} by {interaction.user.mention}")

# /events create
@tournament.command(name="events_create", description="Create a tournament event")
@app_commands.describe(
    team1="Team 1 captain name",
    team2="Team 2 captain name",
    dd="Day (e.g., 25)",
    mm="Month (e.g., 12)",
    yyyy="Year (e.g., 2025)",
    hour="Hour (e.g., 8)",
    minute="Minute (e.g., 30)",
    ampm="AM/PM",
    tour_name="Tournament name",
    group_name="Group name",
    round_no="Round number",
    channel="Event channel",
    captain1="Team 1 captain",
    captain2="Team 2 captain",
    judge="Judge",
    recorder="Recorder",
    image_url="Image URL",
    remarks="Remarks"
)
async def events_create(
    interaction: discord.Interaction,
    team1: str,
    team2: str,
    dd: str,
    mm: str,
    yyyy: str,
    hour: str,
    minute: str,
    ampm: str = None,
    tour_name: str = None,
    group_name: str = None,
    round_no: str = None,
    channel: discord.TextChannel = None,
    captain1: discord.User = None,
    captain2: discord.User = None,
    judge: discord.User = None,
    recorder: discord.User = None,
    image_url: str = None,
    remarks: str = None
):
    tour_name_db = interaction.guild.name.replace(" ", "_").lower()
    db = mongo_client[tour_name_db]
    config = db['config'].find_one({'guild_id': interaction.guild.id})
    if not config:
        await interaction.response.send_message("Config not set! Use /config_set first.", ephemeral=True)
        return

    if not any(role.id == config['bot_op_role'] for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission!", ephemeral=True)
        return

    timestamp = get_timestamp(dd, mm, yyyy, hour, minute, ampm)
    if not timestamp:
        await interaction.response.send_message("Invalid date/time format!", ephemeral=True)
        return
    time_str = f"{dd}/{mm}/{yyyy} {hour}:{minute} {'AM' if ampm and ampm.lower() == 'am' else 'PM'}"

    embed = discord.Embed(
        title=f":calendar_spiral: {team1} vs {team2}",
        color=discord.Color.blue()
    )
    embed.add_field(name="UTC Time", value=time_str, inline=False)
    embed.add_field(name="Local Time", value=f"<t:{timestamp}> (<t:{timestamp}:R>)", inline=False)
    embed.add_field(name="Tournament", value=tour_name or "Not specified", inline=True)
    embed.add_field(name="Group", value=group_name or "Not specified", inline=True)
    embed.add_field(name="Round", value=round_no or "Not specified", inline=True)
    embed.add_field(name="Channel", value=channel.mention if channel else "Not specified", inline=False)
    embed.add_field(name="Team1 Captain", value=captain1.mention if captain1 else team1, inline=True)
    embed.add_field(name="Team2 Captain", value=captain2.mention if captain2 else team2, inline=True)
    embed.add_field(name="Staffs", value=(
        f":white_small_square: **Judge**: {judge.mention if judge else 'Awaiting selection'}\n"
        f":white_small_square: **Recorder**: {recorder.mention if recorder else 'Awaiting selection'}"
    ), inline=False)
    if remarks:
        embed.add_field(name="Remarks", value=remarks, inline=False)
    if image_url:
        embed.set_image(url=image_url)

    class TournamentButtons(discord.ui.View):
        def __init__(self, judge_role_id, recorder_role_id, channel_id):
            super().__init__(timeout=None)
            self.judge_role_id = judge_role_id
            self.recorder_role_id = recorder_role_id
            self.channel_id = channel_id

        @discord.ui.button(label="Judge", style=discord.ButtonStyle.primary)
        async def judge_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not any(role.id == self.judge_role_id for role in interaction.user.roles):
                await interaction.response.send_message("You don't have the Judge role!", ephemeral=True)
                return
            embed.set_field_at(6, name="Staffs", value=(
                f":white_small_square: **Judge**: {interaction.user.mention} ({interaction.user.name})\n"
                f":white_small_square: **Recorder**: {embed.fields[6].value.split('Recorder: ')[1]}"
            ), inline=False)
            if self.channel_id:
                channel = bot.get_channel(self.channel_id)
                if channel:
                    await channel.set_permissions(interaction.user, view_channel=True, send_messages=True)
            await interaction.response.edit_message(embed=embed)
            db['events'].update_one(
                {'message_id': interaction.message.id},
                {'$set': {'judge_id': interaction.user.id}}
            )
            await interaction.followup.send(f"{interaction.user.mention} assigned as Judge!", ephemeral=True)

        @discord.ui.button(label="Recorder", style=discord.ButtonStyle.primary)
        async def recorder_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not any(role.id == self.recorder_role_id for role in interaction.user.roles):
                await interaction.response.send_message("You don't have the Recorder role!", ephemeral=True)
                return
            embed.set_field_at(6, name="Staffs", value=(
                f":white_small_square: **Judge**: {embed.fields[6].value.split('Judge: ')[1].split('\n')[0]}\n"
                f":white_small_square: **Recorder**: {interaction.user.mention} ({interaction.user.name})"
            ), inline=False)
            if self.channel_id:
                channel = bot.get_channel(self.channel_id)
                if channel:
                    await channel.set_permissions(interaction.user, view_channel=True, send_messages=True)
            await interaction.response.edit_message(embed=embed)
            db['events'].update_one(
                {'message_id': interaction.message.id},
                {'$set': {'recorder_id': interaction.user.id}}
            )
            await interaction.followup.send(f"{interaction.user.mention} assigned as Recorder!", ephemeral=True)

    logo_path = 'images/logo.png'
    thumbnail_path = 'images/thumbnail.png'
    image_path = create_tournament_image(team1, team2, time_str, logo_path, thumbnail_path)

    schedule_channel = bot.get_channel(config['schedule_channel'])
    if not schedule_channel:
        await interaction.response.send_message("Schedule channel not found!", ephemeral=True)
        return

    message = await schedule_channel.send(
        embed=embed,
        view=TournamentButtons(config['judge_role'], config['recorder_role'], channel.id if channel else None),
        file=discord.File(image_path)
    )

    db['events'].insert_one({
        'title': f"{team1} vs {team2}",
        'team1': team1,
        'team2': team2,
        'timestamp': timestamp,
        'tour_name': tour_name,
        'group_name': group_name,
        'round_no': round_no,
        'channel_id': channel.id if channel else None,
        'captain1_id': captain1.id if captain1 else None,
        'captain2_id': captain2.id if captain2 else None,
        'judge_id': judge.id if judge else None,
        'recorder_id': recorder.id if recorder else None,
        'image_url': image_url,
        'remarks': remarks,
        'message_id': message.id
    })

    notification_channel = bot.get_channel(config['notification_channel'])
    if notification_channel:
        await notification_channel.send(f"New event: {team1} vs {team2} created!")
    await log_action(db, interaction, f"Event {team1} vs {team2} created by {interaction.user.mention}")
    await interaction.response.send_message("Event created successfully!", ephemeral=True)

# /events edit
@tournament.command(name="events_edit", description="Edit a tournament event")
@app_commands.describe(
    title="Event title (e.g., 'chok vs chok')",
    team1="Team 1 captain name",
    team2="Team 2 captain name",
    dd="Day (e.g., 25)",
    mm="Month (e.g., 12)",
    yyyy="Year (e.g., 2025)",
    hour="Hour (e.g., 8)",
    minute="Minute (e.g., 30)",
    ampm="AM/PM",
    tour_name="Tournament name",
    group_name="Group name",
    round_no="Round number",
    channel="Event channel",
    captain1="Team 1 captain",
    captain2="Team 2 captain",
    judge="Judge",
    recorder="Recorder",
    image_url="Image URL",
    remarks="Remarks"
)
@app_commands.autocomplete(title=event_autocomplete)
async def events_edit(
    interaction: discord.Interaction,
    title: str,
    team1: str = None,
    team2: str = None,
    dd: str = None,
    mm: str = None,
    yyyy: str = None,
    hour: str = None,
    minute: str = None,
    ampm: str = None,
    tour_name: str = None,
    group_name: str = None,
    round_no: str = None,
    channel: discord.TextChannel = None,
    captain1: discord.User = None,
    captain2: discord.User = None,
    judge: discord.User = None,
    recorder: discord.User = None,
    image_url: str = None,
    remarks: str = None
):
    tour_name_db = interaction.guild.name.replace(" ", "_").lower()
    db = mongo_client[tour_name_db]
    config = db['config'].find_one({'guild_id': interaction.guild.id})
    if not config or not any(role.id == config['bot_op_role'] for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission!", ephemeral=True)
        return

    event = db['events'].find_one({'title': title})
    if not event:
        await interaction.response.send_message("Event not found!", ephemeral=True)
        return

    update_data = {}
    if team1:
        update_data['team1'] = team1
    if team2:
        update_data['team2'] = team2
    if dd and mm and yyyy and hour and minute:
        timestamp = get_timestamp(dd, mm, yyyy, hour, minute, ampm)
        if timestamp:
            update_data['timestamp'] = timestamp
    if tour_name:
        update_data['tour_name'] = tour_name
    if group_name:
        update_data['group_name'] = group_name
    if round_no:
        update_data['round_no'] = round_no
    if channel:
        update_data['channel_id'] = channel.id
    if captain1:
        update_data['captain1_id'] = captain1.id
    if captain2:
        update_data['captain2_id'] = captain2.id
    if judge:
        update_data['judge_id'] = judge.id
    if recorder:
        update_data['recorder_id'] = recorder.id
    if image_url:
        update_data['image_url'] = image_url
    if remarks:
        update_data['remarks'] = remarks

    if update_data:
        new_title = f"{team1 or event['team1']} vs {team2 or event['team2']}"
        update_data['title'] = new_title
        db['events'].update_one({'title': title}, {'$set': update_data})

        schedule_channel = bot.get_channel(config['schedule_channel'])
        if schedule_channel:
            message = await schedule_channel.fetch_message(event['message_id'])
            embed = message.embeds[0]
            embed.title = f":calendar_spiral: {new_title}"
            for i, field in enumerate(embed.fields):
                if field.name == "UTC Time" and timestamp:
                    embed.set_field_at(i, name="UTC Time", value=f"{dd}/{mm}/{yyyy} {hour}:{minute} {ampm or ''}", inline=False)
                elif field.name == "Local Time" and timestamp:
                    embed.set_field_at(i, name="Local Time", value=f"<t:{timestamp}> (<t:{timestamp}:R>)", inline=False)
                elif field.name == "Tournament":
                    embed.set_field_at(i, name="Tournament", value=tour_name or event['tour_name'] or "Not specified", inline=True)
                elif field.name == "Group":
                    embed.set_field_at(i, name="Group", value=group_name or event['group_name'] or "Not specified", inline=True)
                elif field.name == "Round":
                    embed.set_field_at(i, name="Round", value=round_no or event['round_no'] or "Not specified", inline=True)
                elif field.name == "Channel":
                    embed.set_field_at(i, name="Channel", value=channel.mention if channel else "Not specified", inline=False)
                elif field.name == "Team1 Captain":
                    embed.set_field_at(i, name="Team1 Captain", value=captain1.mention if captain1 else team1 or event['team1'], inline=True)
                elif field.name == "Team2 Captain":
                    embed.set_field_at(i, name="Team2 Captain", value=captain2.mention if captain2 else team2 or event['team2'], inline=True)
                elif field.name == "Staffs":
                    embed.set_field_at(i, name="Staffs", value=(
                        f":white_small_square: **Judge**: {judge.mention if judge else event['judge_id'] and bot.get_user(event['judge_id']).mention or 'Awaiting selection'}\n"
                        f":white_small_square: **Recorder**: {recorder.mention if recorder else event['recorder_id'] and bot.get_user(event['recorder_id']).mention or 'Awaiting selection'}"
                    ), inline=False)
                elif field.name == "Remarks":
                    embed.set_field_at(i, name="Remarks", value=remarks or event['remarks'] or "None", inline=False)
            if image_url:
                embed.set_image(url=image_url)
            await message.edit(embed=embed)

        await log_action(db, interaction, f"Event {title} edited by {interaction.user.mention}")
        await interaction.response.send_message("Event updated successfully!", ephemeral=True)
    else:
        await interaction.response.send_message("Please specify at least one field to edit!", ephemeral=True)

# /events delete
@tournament.command(name="events_delete", description="Delete a tournament event")
@app_commands.describe(title="Event title (e.g., 'chok vs chok')", reason="Reason for deletion")
@app_commands.autocomplete(title=event_autocomplete)
async def events_delete(interaction: discord.Interaction, title: str, reason: str = None):
    tour_name_db = interaction.guild.name.replace(" ", "_").lower()
    db = mongo_client[tour_name_db]
    config = db['config'].find_one({'guild_id': interaction.guild.id})
    if not config or not any(role.id == config['bot_op_role'] for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission!", ephemeral=True)
        return

    event = db['events'].find_one({'title': title})
    if not event:
        await interaction.response.send_message("Event not found!", ephemeral=True)
        return

    class ConfirmDelete(discord.ui.View):
        @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
        async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            db['events'].delete_one({'title': title})
            schedule_channel = bot.get_channel(config['schedule_channel'])
            if schedule_channel and event['message_id']:
                message = await schedule_channel.fetch_message(event['message_id'])
                await message.delete()
            await log_action(db, interaction, f"Event {title} deleted by {interaction.user.mention}. Reason: {reason or 'None'}")
            await interaction.response.edit_message(content="Event deleted successfully!", view=None)

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.edit_message(content="Deletion cancelled.", view=None)

    await interaction.response.send_message(f"Confirm deletion of event '{title}'?", view=ConfirmDelete(), ephemeral=True)

# /events show
@tournament.command(name="events_show", description="Show event details")
@app_commands.describe(title="Event title (e.g., 'chok vs chok')")
@app_commands.autocomplete(title=event_autocomplete)
async def events_show(interaction: discord.Interaction, title: str):
    tour_name_db = interaction.guild.name.replace(" ", "_").lower()
    db = mongo_client[tour_name_db]
    config = db['config'].find_one({'guild_id': interaction.guild.id})
    if not config:
        await interaction.response.send_message("Config not set! Use /config_set first.", ephemeral=True)
        return

    event = db['events'].find_one({'title': title})
    if not event:
        await interaction.response.send_message("Event not found!", ephemeral=True)
        return

    embed = discord.Embed(title=f":calendar_spiral: {event['title']}", color=discord.Color.blue())
    embed.add_field(name="UTC Time", value=datetime.fromtimestamp(event['timestamp']).strftime('%d/%m/%Y %H:%M'), inline=False)
    embed.add_field(name="Local Time", value=f"<t:{event['timestamp']}> (<t:{event['timestamp']}:R>)", inline=False)
    embed.add_field(name="Tournament", value=event['tour_name'] or "Not specified", inline=True)
    embed.add_field(name="Group", value=event['group_name'] or "Not specified", inline=True)
    embed.add_field(name="Round", value=event['round_no'] or "Not specified", inline=True)
    embed.add_field(name="Channel", value=f"<#{event['channel_id']}>" if event['channel_id'] else "Not specified", inline=False)
    embed.add_field(name="Team1 Captain", value=bot.get_user(event['captain1_id']).mention if event['captain1_id'] else event['team1'], inline=True)
    embed.add_field(name="Team2 Captain", value=bot.get_user(event['captain2_id']).mention if event['captain2_id'] else event['team2'], inline=True)
    embed.add_field(name="Staffs", value=(
        f":white_small_square: **Judge**: {bot.get_user(event['judge_id']).mention if event['judge_id'] else 'Awaiting selection'}\n"
        f":white_small_square: **Recorder**: {bot.get_user(event['recorder_id']).mention if event['recorder_id'] else 'Awaiting selection'}"
    ), inline=False)
    if event['remarks']:
        embed.add_field(name="Remarks", value=event['remarks'], inline=False)
    if event['image_url']:
        embed.set_image(url=event['image_url'])

    await interaction.response.send_message(embed=embed, ephemeral=True)
    await log_action(db, interaction, f"Event {title} viewed by {interaction.user.mention}")

# /events results
@tournament.command(name="events_results", description="Submit event results")
@app_commands.describe(
    event="Event title (e.g., 'chok vs chok')",
    team1_score="Team 1 score",
    team2_score="Team 2 score",
    number_of_matches="Number of matches",
    remarks="Additional remarks",
    rec_link="Recording link",
    screenshot1="Screenshot 1 URL",
    screenshot2="Screenshot 2 URL",
    screenshot3="Screenshot 3 URL",
    screenshot4="Screenshot 4 URL",
    screenshot5="Screenshot 5 URL",
    screenshot6="Screenshot 6 URL",
    screenshot7="Screenshot 7 URL",
    screenshot8="Screenshot 8 URL",
    screenshot9="Screenshot 9 URL"
)
@app_commands.autocomplete(event=event_autocomplete)
async def events_results(
    interaction: discord.Interaction,
    event: str,
    team1_score: int,
    team2_score: int,
    number_of_matches: int,
    remarks: str = None,
    rec_link: str = None,
    screenshot1: str = None,
    screenshot2: str = None,
    screenshot3: str = None,
    screenshot4: str = None,
    screenshot5: str = None,
    screenshot6: str = None,
    screenshot7: str = None,
    screenshot8: str = None,
    screenshot9: str = None
):
    tour_name_db = interaction.guild.name.replace(" ", "_").lower()
    db = mongo_client[tour_name_db]
    config = db['config'].find_one({'guild_id': interaction.guild.id})
    if not config or not any(role.id == config['bot_op_role'] for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission!", ephemeral=True)
        return

    event_data = db['events'].find_one({'title': event})
    if not event_data:
        await interaction.response.send_message("Event not found!", ephemeral=True)
        return

    results_channel = bot.get_channel(config['results_channel'])
    if not results_channel:
        await interaction.response.send_message("Results channel not found!", ephemeral=True)
        return

    embed = discord.Embed(title=f"{event_data['team1']} vs {event_data['team2']}", color=discord.Color.green())
    embed.add_field(name="Local Time", value=f"<t:{event_data['timestamp']}> (<t:{event_data['timestamp']}:R>)", inline=False)
    embed.add_field(name="Tournament", value=event_data['tour_name'] or "Not specified", inline=True)
    embed.add_field(name="Group", value=event_data['group_name'] or "Not specified", inline=True)
    embed.add_field(name="Round", value=event_data['round_no'] or "Not specified", inline=True)
    embed.add_field(name="Channel", value=f"<#{event_data['channel_id']}>" if event_data['channel_id'] else "Not specified", inline=False)
    embed.add_field(name="Team1 Captain", value=bot.get_user(event_data['captain1_id']).mention if event_data['captain1_id'] else event_data['team1'], inline=True)
    embed.add_field(name="Team2 Captain", value=bot.get_user(event_data['captain2_id']).mention if event_data['captain2_id'] else event_data['team2'], inline=True)
    embed.add_field(name="Staffs", value=(
        f":white_small_square: **Judge**: {bot.get_user(event_data['judge_id']).mention if event_data['judge_id'] else 'Awaiting selection'}\n"
        f":white_small_square: **Recorder**: {bot.get_user(event_data['recorder_id']).mention if event_data['recorder_id'] else 'Awaiting selection'}"
    ), inline=False)
    winner = "Team1" if team1_score > team2_score else "Team2" if team2_score > team1_score else "Draw"
    embed.add_field(name="Results", value=(
        f"{'💀' if winner != 'Team1' else '🏆'} {event_data['team1']} ({team1_score}) : ({team2_score}) {event_data['team2']} {'🏆' if winner == 'Team2' else '💀'}"
    ), inline=False)
    if rec_link:
        embed.add_field(name="Recorder Link", value=rec_link, inline=False)
    if remarks:
        embed.add_field(name="Remarks", value=remarks, inline=False)
    if screenshot1:
        embed.set_image(url=screenshot1)

    screenshots = [s for s in [screenshot2, screenshot3, screenshot4, screenshot5, screenshot6, screenshot7, screenshot8, screenshot9] if s]
    if screenshots:
        await results_channel.send("\n".join(screenshots))
    await results_channel.send(embed=embed)

    db['results'].insert_one({
        'event_title': event,
        'team1_score': team1_score,
        'team2_score': team2_score,
        'number_of_matches': number_of_matches,
        'remarks': remarks,
        'rec_link': rec_link,
        'screenshots': [screenshot1] + screenshots if screenshot1 else screenshots,
        'timestamp': datetime.utcnow()
    })
    await log_action(db, interaction, f"Results for {event} submitted by {interaction.user.mention}")
    await interaction.response.send_message("Results submitted successfully!", ephemeral=True)

# /events list
@tournament.command(name="events_list", description="List all tournament events")
async def events_list(interaction: discord.Interaction):
    tour_name_db = interaction.guild.name.replace(" ", "_").lower()
    db = mongo_client[tour_name_db]
    config = db['config'].find_one({'guild_id': interaction.guild.id})
    if not config:
        await interaction.response.send_message("Config not set! Use /config_set first.", ephemeral=True)
        return

    events = db['events'].find()
    event_list = [f"- {event['title']} (<t:{event['timestamp']}:R>)" for event in events]
    if not event_list:
        await interaction.response.send_message("No events found!", ephemeral=True)
        return

    embed = discord.Embed(title="Tournament Events", description="\n".join(event_list), color=discord.Color.purple())
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await log_action(db, interaction, f"Event list viewed by {interaction.user.mention}")

# Log action to transcript channel
async def log_action(db, interaction, message):
    config = db['config'].find_one({'guild_id': interaction.guild.id})
    if config and config['transcript_channel']:
        transcript_channel = bot.get_channel(config['transcript_channel'])
        if transcript_channel:
            await transcript_channel.send(message)

# Run bot
bot.run(DISCORD_TOKEN)
