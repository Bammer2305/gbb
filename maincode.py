import sys
import traceback
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import datetime
import json
import os

from dotenv import load_dotenv

# --- CONFIG ---
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
print("TOKEN:", TOKEN)  # temporary debug
bot.run(TOKEN)

TOKEN = os.getenv("DISCORD_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID"))


PREFIX = "!"
TEST_GUILD_ID = None  # <-- set to a guild ID to instantly register slash commands
BANS_FILE = "globalbans.json"
# ------------------------------------------

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
start_time = datetime.datetime.utcnow()


# --- Ban storage (self-healing JSON) ---
def load_bans():
    if not os.path.exists(BANS_FILE):
        with open(BANS_FILE, "w") as f:
            f.write("{}")
    try:
        with open(BANS_FILE, "r") as f:
            data = f.read().strip()
            if not data:
                return {}
            return json.loads(data)
    except json.JSONDecodeError:
        with open(BANS_FILE, "w") as f:
            f.write("{}")
        return {}


def save_bans(data):
    with open(BANS_FILE, "w") as f:
        json.dump(data, f, indent=4)


# --- Logging helper ---
async def send_log(embed: discord.Embed):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[WARN] Could not send to log channel: {e}")


# --- Role check ---
def member_has_staff_role(member: discord.Member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    return any(r.id == STAFF_ROLE_ID for r in member.roles)


# --- Global Ban Command ---
@bot.hybrid_command(name="globalban", description="Globally ban a user from all servers")
async def globalban(ctx, user: discord.User, *, reason: str = "No reason provided"):
    member = ctx.author if isinstance(ctx.author, discord.Member) else None
    if not member or not member_has_staff_role(member):
        return await ctx.send("❌ You don't have permission to use this command.")

    bans = load_bans()
    bans[str(user.id)] = {
        "reason": reason,
        "banned_by": f"{ctx.author} ({ctx.author.id})",
        "time": datetime.datetime.utcnow().isoformat()
    }
    save_bans(bans)

    succeeded, failed = [], []
    for guild in bot.guilds:
        try:
            await guild.ban(user, reason=f"[GlobalBan] {reason}")
            succeeded.append(guild.name)
        except Exception as e:
            failed.append(f"{guild.name} ({type(e).__name__})")

    embed = discord.Embed(
        title="🌐 Global Ban Issued",
        description=f"{user.mention} has been globally banned.",
        color=discord.Color.red(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="👤 User", value=f"{user} (`{user.id}`)", inline=False)
    embed.add_field(name="📄 Reason", value=reason, inline=False)
    embed.add_field(name="🛡️ Banned By", value=ctx.author.mention, inline=False)
    if succeeded:
        embed.add_field(name="✅ Banned In", value="\n".join(succeeded)[:1024], inline=False)
    if failed:
        embed.add_field(name="⚠️ Failed", value="\n".join(failed)[:1024], inline=False)
    embed.set_footer(text=f"Action by {ctx.author}", icon_url=ctx.author.display_avatar.url)

    await ctx.send(embed=embed)
    await send_log(embed)


# --- Global Unban Command ---
@bot.hybrid_command(name="globalunban", description="Globally unban a user from all servers")
async def globalunban(ctx, user: discord.User):
    member = ctx.author if isinstance(ctx.author, discord.Member) else None
    if not member or not member_has_staff_role(member):
        return await ctx.send("❌ You don't have permission to use this command.")

    bans = load_bans()
    bans.pop(str(user.id), None)
    save_bans(bans)

    succeeded, failed = [], []
    for guild in bot.guilds:
        try:
            await guild.unban(user)
            succeeded.append(guild.name)
        except Exception as e:
            failed.append(f"{guild.name} ({type(e).__name__})")

    embed = discord.Embed(
        title="✅ Global Unban Issued",
        description=f"{user.mention} has been globally unbanned.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="👤 User", value=f"{user} (`{user.id}`)", inline=False)
    embed.add_field(name="🛡️ Unbanned By", value=ctx.author.mention, inline=False)
    if succeeded:
        embed.add_field(name="✅ Unbanned In", value="\n".join(succeeded)[:1024], inline=False)
    if failed:
        embed.add_field(name="⚠️ Failed", value="\n".join(failed)[:1024], inline=False)
    embed.set_footer(text=f"Action by {ctx.author}", icon_url=ctx.author.display_avatar.url)

    await ctx.send(embed=embed)
    await send_log(embed)


# --- Servers Command ---
@bot.command(name="servers")
async def servers_cmd(ctx):
    guilds = bot.guilds
    total = len(guilds)

    embed = discord.Embed(
        title="📜 Connected Servers",
        description=f"The bot is currently in **{total}** servers.",
        color=discord.Color.blurple(),
        timestamp=datetime.datetime.utcnow()
    )

    listed = ""
    for g in guilds[:10]:
        listed += f"**{g.name}** (`{g.id}`) – 👥 {g.member_count}\n"

    embed.add_field(
        name="Servers",
        value=listed or "No servers found.",
        inline=False
    )

    if total > 10:
        embed.set_footer(text=f"...and {total - 10} more servers")
    else:
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)

    await ctx.send(embed=embed)


# --- Uptime Command ---
@bot.command(name="uptime")
async def uptime_cmd(ctx):
    delta = datetime.datetime.utcnow() - start_time
    total_seconds = int(delta.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    embed = discord.Embed(title="⏱ Bot Uptime", color=discord.Color.purple())
    embed.add_field(name="Uptime", value=f"{hours}h {minutes}m {seconds}s")
    await ctx.send(embed=embed)


# --- On Ready ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (id: {bot.user.id})")
    try:
        if TEST_GUILD_ID:
            await bot.tree.sync(guild=discord.Object(id=TEST_GUILD_ID))
            print(f"✅ Slash commands synced to test guild {TEST_GUILD_ID}")
        else:
            await bot.tree.sync()
            print("✅ Global slash commands synced (may take up to 1h to appear)")
    except Exception as e:
        print("❌ Failed to sync slash commands:", e)
        traceback.print_exc()


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    raise error


# --- Run ---
if TOKEN is None:
    print("❌ ERROR: No bot token found. Set TOKEN as an environment variable.")
    sys.exit(1)

bot.run(TOKEN)

