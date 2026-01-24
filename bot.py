import discord
from discord.ext import commands
from discord import app_commands
import random
import string
import json
import os
import asyncio
from datetime import datetime, timedelta
import openai
import aiohttp
import base64
from dotenv import load_dotenv

# --- CARGAR VARIABLES DE ENTORNO ---
load_dotenv()

# Función auxiliar para convertir variables de entorno a enteros de forma segura
def get_env_int(var_name):
    value = os.getenv(var_name)
    if value is None:
        print(f"⚠️ ADVERTENCIA: La variable {var_name} no está en el archivo .env")
        return 0
    return int(value)

# --- CONFIGURACIÓN ---
GUILD_ID = get_env_int("GUILD_ID")
LIMITED_ROLE_ID = get_env_int("LIMITED_ROLE_ID")
LOGIN_CHANNEL_ID = get_env_int("LOGIN_CHANNEL_ID")
VOICE_CREATOR_ID = get_env_int("VOICE_CREATOR_ID")
AI_CHANNEL_ID = get_env_int("AI_CHANNEL_ID")
PINNED_RESPONSE_CHANNEL_ID = get_env_int("PINNED_RESPONSE_CHANNEL_ID")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o") # Por defecto usa gpt-4o si no está en .env

# --- DATOS PERSISTENTES ---
DATA_FILE = os.getenv("DATA_FILE", "bender_data.json")

def load_data():
    defaults = {
        "codes": [], 
        "user_channels": {}, 
        "ghost_mode": {},
        "failed_attempts": {},
        "timeout_until": {},
        "conversation_history": [],
        "voice_control_messages": {},
        "active_voice_channels": {},
        "voice_channel_owners": {},
        "member_join_times": {},
        "owner_left_tasks": {},
        "channel_modes": {},        
        "crystal_permits": {}      
    }
    
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                saved_data = json.load(f)
                modified = False
                for key, value in defaults.items():
                    if key not in saved_data:
                        saved_data[key] = value
                        modified = True
                if modified:
                    with open(DATA_FILE, 'w') as fw:
                        json.dump(saved_data, fw, indent=4)
                return saved_data
        except Exception as e:
            print(f"Error cargando JSON, creando uno nuevo: {e}")
            return defaults
    return defaults

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

data = load_data()

# --- BOT SETUP ---
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
openai.api_key = OPENAI_API_KEY
voice_creation_locks = {}

# --- ROLES Y EMOJIS (CONFIGURACIÓN MANUAL) ---
# ⚠️ IMPORTANTE: Edita estos IDs con los de tu servidor antes de correr el bot
COLOR_ROLES = {
    "<:blood:1432460543695786045>": 1432438827473174538, # ID del Rol Blood
    "<:caca:1432460577040633977>": 1432438922537074889,  # ID del Rol Caca
    "<:weed:1432460901327306883>": 1432438953939566592,  # ID del Rol Weed
    "<:ice:1432461184841289768>": 1432438970310066397,   # ID del Rol Ice
    "<:haze:1432472281547935865>": 1432438981944934432,  # ID del Rol Haze
    "<:pig:1432462018836959316>": 1432438994624450621,   # ID del Rol Pig
    "<:vamp:1432462278183227393>": 1432439009673613412,  # ID del Rol Vamp
    "<:KKK:1432462725333909596>": 1432439022508179456,   # ID del Rol Milky
    "<:spain:1432462796175704064>": 1432439040031854643, # ID del Rol España
    "<:thunder:1432463581101817957>": 1432439652278730864, # ID del Rol Thunder
    "<:EUR:1432463602161549504>": 1432458310145015940    # ID del Rol Rich
}
# Filtramos roles que sean None o 0 por seguridad
EMOJI_TO_ROLE = {emoji: role_id for emoji, role_id in COLOR_ROLES.items() if role_id is not None and role_id != 0}

SERVER_CONTEXT = """
Eres Bender, el bot del servidor Chepa 2.0.
Tu personalidad: Borde, sarcástico, directo, insultante si es necesario, pero útil.
"""

# --- FUNCIONES AUXILIARES ---

async def search_web(query):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.duckduckgo.com/?q={query}&format=json"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = []
                    if data.get('Abstract'): results.append(f"**Resumen:** {data['Abstract']}")
                    if data.get('RelatedTopics'):
                        for topic in data['RelatedTopics'][:3]:
                            if isinstance(topic, dict) and 'Text' in topic: results.append(f"- {topic['Text']}")
                    return "\n".join(results) if results else "No encontré una mierda."
    except Exception as e: return f"Error buscando: {str(e)}"

async def analyze_image(image_url, question=None):
    try:
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": question if question else "Qué coño es esto?"},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        }]
        response = openai.ChatCompletion.create(model=OPENAI_MODEL, messages=messages, max_tokens=500)
        return response['choices'][0]['message']['content']
    except Exception as e: return f"Error viendo la foto: {str(e)}"

def generate_code():
    parts = [
        ''.join(random.choices(string.ascii_uppercase + string.digits, k=3)),
        ''.join(random.choices(string.ascii_uppercase + string.digits, k=2)),
        ''.join(random.choices(string.ascii_uppercase + string.digits, k=3)),
        ''.join(random.choices(string.ascii_uppercase + string.digits, k=2))
    ]
    return '-'.join(parts)

# --- PERMISOS Y CONTROL DE CANALES ---

async def update_channel_permissions(channel, mode, allowed_users, guild):
    owner_id = data["voice_channel_owners"].get(str(channel.id))
    if not owner_id: return
    owner = guild.get_member(owner_id)
    limited_role = guild.get_role(LIMITED_ROLE_ID)
    
    # 1. Base: Nadie entra ni ve
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False),
        guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, move_members=True)
    }
    
    if owner:
        overwrites[owner] = discord.PermissionOverwrite(connect=True, view_channel=True, move_members=True, manage_channels=True)
    
    if limited_role:
        overwrites[limited_role] = discord.PermissionOverwrite(connect=False, view_channel=False)

    # 2. Configurar Modos
    if mode == "public":
        overwrites[guild.default_role] = discord.PermissionOverwrite(connect=True, view_channel=True)
        if limited_role: overwrites[limited_role] = discord.PermissionOverwrite(connect=False, view_channel=False)

    elif mode == "ghost" or mode == "crystal":
        overwrites[guild.default_role] = discord.PermissionOverwrite(connect=False, view_channel=False)
        for uid in allowed_users:
            member = guild.get_member(uid)
            if member:
                overwrites[member] = discord.PermissionOverwrite(connect=True, view_channel=True)

    # 3. Aplicar
    try: await channel.edit(overwrites=overwrites)
    except Exception as e: print(f"Error permisos: {e}")

    # 4. KICK INTELIGENTE
    if mode == "crystal" or mode == "ghost":
        for member in channel.members:
            if member.id == owner_id or member.bot: continue
            if member.id not in allowed_users:
                try: 
                    await member.move_to(None)
                    print(f"🥾 Kickeado {member.display_name} por no tener permiso.")
                except: pass

async def cleanup_pending_transfer(channel_id, guild):
    keys_to_remove = []
    for task_id, task_data in data.get("owner_left_tasks", {}).items():
        if task_data["channel_id"] == channel_id:
            try:
                temp_channel = guild.get_channel(task_data["temp_message_channel_id"])
                if temp_channel:
                    msg = await temp_channel.fetch_message(task_data["temp_message_id"])
                    await msg.delete()
            except: pass
            keys_to_remove.append(task_id)
    
    for k in keys_to_remove: del data["owner_left_tasks"][k]
    if keys_to_remove: save_data(data)

async def delete_control_message(user_id, guild):
    uid = str(user_id)
    if uid in data.get("voice_control_messages", {}):
        c_data = data["voice_control_messages"][uid]
        if uid in data["user_channels"]:
            ud = data["user_channels"][uid]
            chid = ud["channel_id"] if isinstance(ud, dict) else ud
            ch = guild.get_channel(chid)
            if ch:
                try:
                    msg = await ch.fetch_message(c_data["message_id"])
                    await msg.delete()
                except: pass
        del data["voice_control_messages"][uid]
        save_data(data)

async def cleanup_orphaned_channels(guild):
    for channel in guild.voice_channels:
        if channel.name.startswith("⛧︲") and channel.id != VOICE_CREATOR_ID:
            if len(channel.members) == 0:
                try: await channel.delete()
                except: pass
    
    data["active_voice_channels"] = {}
    data["voice_control_messages"] = {}
    data["voice_channel_owners"] = {}
    data["member_join_times"] = {}
    data["owner_left_tasks"] = {}
    save_data(data)

# --- CREACIÓN DE CANALES ---

async def create_self_channel(member, guild):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member: discord.PermissionOverwrite(read_messages=True, send_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, embed_links=True)
    }
    
    channel = await guild.create_text_channel(f"⛧︲self", overwrites=overwrites)
    
    data["user_channels"][str(member.id)] = {"channel_id": channel.id, "color_msg_id": None}
    data["ghost_mode"][str(member.id)] = False
    save_data(data)
    
    current_role = None
    for emoji, role_id in COLOR_ROLES.items():
        role = guild.get_role(role_id)
        if role and role in member.roles:
            current_role = emoji
            break
            
    embed = discord.Embed(
        title="⛧ SELECCIÓN DE IDENTIDAD",
        description="```ansi\n\u001b[1;37mReacciona con el símbolo de tu esencia.\n\u001b[0;31m⚠ Solo puedes portar una identidad a la vez.\u001b[0m\n```",
        color=0x000000
    )
    val = f"```fix\n{current_role} ACTIVO\n```" if current_role else "```diff\n- SIN IDENTIDAD ASIGNADA\n```"
    embed.add_field(name="╔═══ IDENTIDAD ACTUAL ═══╗", value=val, inline=False)
    
    role_names = {
        "<:blood:1432460543695786045>": "**BLOOD** ─ Sangre oscura",
        "<:caca:1432460577040633977>": "**CACA** ─ Naturaleza bruta",
        "<:weed:1432460901327306883>": "**WEED** ─ Mente expandida",
        "<:ice:1432461184841289768>": "**ICE** ─ Frialdad absoluta",
        "<:haze:1432472281547935865>": "**HAZE** ─ Neblina mental",
        "<:pig:1432462018836959316>": "**PIG** ─ Glutonería pura",
        "<:vamp:1432462278183227393>": "**VAMP** ─ Sed nocturna",
        "<:KKK:1432462725333909596>": "**MILKY** ─ Pureza láctea",
        "<:spain:1432462796175704064>": "**ESPAÑA** ─ Orgullo ibérico",
        "<:thunder:1432463581101817957>": "**THUNDER** ─ Poder eléctrico",
        "<:EUR:1432463602161549504>": "**RICH** ─ Riqueza suprema"
    }
    legend = [f"{e} ⟩ {role_names.get(e, '**ROL**')}" for e in COLOR_ROLES.keys() if COLOR_ROLES[e]]
    embed.add_field(name="╠═══ IDENTIDADES DISPONIBLES ═══╣", value="\n".join(legend) if legend else "None", inline=False)
    embed.set_footer(text="⛧ Reacciona para cambiar • Actualización automática ⛧")
    
    msg = await channel.send(embed=embed)
    for emoji in COLOR_ROLES.keys():
        try: await msg.add_reaction(emoji)
        except: pass
        
    data["user_channels"][str(member.id)]["color_msg_id"] = msg.id
    save_data(data)
    return channel

async def create_voice_control_panel(member, voice_channel, guild):
    user_id = str(member.id)
    current_mode = data.get("channel_modes", {}).get(str(voice_channel.id), "public")
    
    if user_id in data["user_channels"]:
        ud = data["user_channels"][user_id]
        chid = ud["channel_id"] if isinstance(ud, dict) else ud
        ch = guild.get_channel(chid)
        
        if ch:
            color = 0x2ecc71 if current_mode == "public" else (0x95a5a6 if current_mode == "ghost" else 0x9b59b6)
            mode_text = "🔮 CRISTAL" if current_mode == "crystal" else ("👻 FANTASMA" if current_mode == "ghost" else "🌍 PÚBLICO")

            embed = discord.Embed(
                title="⛧ CONTROL DE CANAL DE VOZ",
                description=f"Canal: {voice_channel.mention}\n\n**Estado Actual:** {mode_text}\nUsa los botones para gestionar tu canal.",
                color=color
            )
            embed.set_footer(text="El panel se elimina al salir del canal")
            
            view = VoiceControlView(member, voice_channel, mode=current_mode)
            control_msg = await ch.send(embed=embed, view=view)
            
            data["voice_control_messages"][user_id] = {
                "message_id": control_msg.id,
                "voice_channel_id": voice_channel.id
            }
            save_data(data)

async def handle_owner_left(voice_channel, old_owner_id, guild):
    old_owner = guild.get_member(old_owner_id)
    await delete_control_message(old_owner_id, guild)
    
    current_members = [m for m in voice_channel.members if m.id != old_owner_id]
    
    ud = data["user_channels"].get(str(old_owner_id))
    if ud:
        chid = ud["channel_id"] if isinstance(ud, dict) else ud
        ch = guild.get_channel(chid)
        if ch:
            embed = discord.Embed(
                title="⚠️ OWNER DESCONECTADO",
                description=f"**{old_owner.display_name}** ha abandonado {voice_channel.mention}\n\nTienes **5 minutos** para elegir un nuevo administrador.",
                color=0xFF6B35, timestamp=datetime.now()
            )
            view = OwnerTransferView(old_owner, voice_channel, current_members)
            temp_msg = await ch.send(embed=embed, view=view)
            
            task_id = f"{voice_channel.id}_{old_owner_id}"
            data["owner_left_tasks"][task_id] = {
                "channel_id": voice_channel.id,
                "old_owner_id": old_owner_id,
                "temp_message_id": temp_msg.id,
                "temp_message_channel_id": ch.id,
                "timestamp": datetime.now().isoformat()
            }
            save_data(data)
            asyncio.create_task(handle_owner_timeout(task_id, voice_channel, old_owner_id, guild, temp_msg))

async def handle_owner_timeout(task_id, voice_channel, old_owner_id, guild, temp_msg):
    await asyncio.sleep(300)
    if task_id not in data.get("owner_left_tasks", {}): return

    try: voice_channel = await guild.fetch_channel(voice_channel.id)
    except:
        del data["owner_left_tasks"][task_id]; save_data(data)
        return

    old_owner = guild.get_member(old_owner_id)
    if old_owner and old_owner in voice_channel.members:
        data["voice_channel_owners"][str(voice_channel.id)] = old_owner_id
        await create_voice_control_panel(old_owner, voice_channel, guild)
        del data["owner_left_tasks"][task_id]; save_data(data)
        try: await temp_msg.delete()
        except: pass
        return

    current_members = [m for m in voice_channel.members if m.id != old_owner_id]
    if not current_members:
        try: await voice_channel.delete()
        except: pass
        del data["owner_left_tasks"][task_id]
        save_data(data)
        try: await temp_msg.delete()
        except: pass
        return

    new_owner = current_members[0]
    data["voice_channel_owners"][str(voice_channel.id)] = new_owner.id
    await create_voice_control_panel(new_owner, voice_channel, guild)
    
    del data["owner_left_tasks"][task_id]
    save_data(data)
    try: await temp_msg.delete()
    except: pass

# --- VISTAS / INTERFAZ ---

class VoiceControlView(discord.ui.View):
    def __init__(self, owner, voice_channel, mode="public"):
        super().__init__(timeout=None)
        self.owner = owner
        self.voice_channel = voice_channel
        self.mode = mode
        self.update_buttons()

    def update_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id == "mode_btn":
                if self.mode == "public":
                    child.label = "PÚBLICO"
                    child.emoji = "🌍"
                    child.style = discord.ButtonStyle.green
                elif self.mode == "ghost":
                    child.label = "FANTASMA"
                    child.emoji = "👻"
                    child.style = discord.ButtonStyle.secondary
                elif self.mode == "crystal":
                    child.label = "CRISTAL"
                    child.emoji = "🔮"
                    child.style = discord.ButtonStyle.primary
        
        has_select = any(isinstance(child, discord.ui.UserSelect) for child in self.children)
        if self.mode == "crystal" and not has_select:
            self.add_item(CrystalAccessSelect(self.voice_channel))
        elif self.mode != "crystal" and has_select:
            for child in self.children:
                if isinstance(child, discord.ui.UserSelect): self.remove_item(child)

    @discord.ui.button(custom_id="mode_btn", label="Modo: PÚBLICO", style=discord.ButtonStyle.green, emoji="🌍", row=0)
    async def cycle_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner.id: return await interaction.response.send_message("❌ No eres el dueño.", ephemeral=True)

        if self.mode == "public":
            self.mode = "ghost"
            next_txt = "👻 FANTASMA (Invisible)"
        elif self.mode == "ghost":
            self.mode = "crystal"
            next_txt = "🔮 CRISTAL (Visible pero Privado)"
        else:
            self.mode = "public"
            next_txt = "🌍 PÚBLICO (Abierto)"

        cid = str(self.voice_channel.id)
        if self.mode in ["ghost", "crystal"]:
            current_members_ids = [m.id for m in self.voice_channel.members if m.id != self.owner.id]
            
            if "crystal_permits" not in data: data["crystal_permits"] = {}
            existing_permits = data["crystal_permits"].get(cid, [])
            
            new_permits = list(set(existing_permits + current_members_ids))
            data["crystal_permits"][cid] = new_permits
        
        data["channel_modes"][cid] = self.mode
        save_data(data)

        allowed = data.get("crystal_permits", {}).get(cid, [])
        await update_channel_permissions(self.voice_channel, self.mode, allowed, interaction.guild)

        self.update_buttons()
        embed = interaction.message.embeds[0]
        embed.color = 0x9b59b6 if self.mode == "crystal" else (0x2ecc71 if self.mode == "public" else 0x95a5a6)
        embed.description = f"Canal: {self.voice_channel.mention}\n\n**Estado Actual:** {next_txt}\nUsa el menú abajo para gestionar acceso."
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger, emoji="💣", row=0)
    async def kick_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner.id: return
        members = [m for m in self.voice_channel.members if m.id != self.owner.id]
        if not members: return await interaction.response.send_message("Nadie para kickear", ephemeral=True)
        view = KickSelectView(self.owner, self.voice_channel, members)
        await interaction.response.send_message("Selecciona a la víctima:", view=view, ephemeral=True)

    @discord.ui.button(label="Renombrar", style=discord.ButtonStyle.secondary, emoji="🧿", row=0)
    async def change_name(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner.id: return
        await interaction.response.send_modal(ChangeNameModal(self.owner, self.voice_channel))

class CrystalAccessSelect(discord.ui.UserSelect):
    def __init__(self, voice_channel):
        super().__init__(placeholder="🔮 Gestionar Acceso Cristal (Añadir/Quitar)", min_values=1, max_values=10, row=1)
        self.voice_channel = voice_channel

    async def callback(self, interaction: discord.Interaction):
        cid = str(self.voice_channel.id)
        if "crystal_permits" not in data: data["crystal_permits"] = {}
        current = data["crystal_permits"].get(cid, [])
        changes = []
        
        for member in self.values:
            if member.id in current:
                current.remove(member.id)
                changes.append(f"⛔ {member.display_name} (Revocado)")
            else:
                current.append(member.id)
                changes.append(f"✅ {member.display_name} (Permitido)")
        
        data["crystal_permits"][cid] = current
        save_data(data)
        
        mode = data.get("channel_modes", {}).get(cid, "crystal")
        await update_channel_permissions(self.voice_channel, mode, current, interaction.guild)
        
        await interaction.response.send_message(f"Permisos Cristal Actualizados:\n" + "\n".join(changes), ephemeral=True)

class KickSelectView(discord.ui.View):
    def __init__(self, owner, voice_channel, members):
        super().__init__(timeout=60)
        self.owner = owner; self.voice_channel = voice_channel
        self.add_item(KickSelect(owner, voice_channel, members))

class KickSelect(discord.ui.Select):
    def __init__(self, owner, voice_channel, members):
        options = [discord.SelectOption(label=m.display_name, value=str(m.id)) for m in members[:25]]
        super().__init__(placeholder="Selecciona usuario", options=options)
        self.owner = owner; self.voice_channel = voice_channel
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner.id: return
        m = interaction.guild.get_member(int(self.values[0]))
        if m and m.voice.channel == self.voice_channel:
            await m.move_to(None)
            await interaction.response.send_message(f"💣 {m.display_name} expulsado", ephemeral=True)

class ChangeNameModal(discord.ui.Modal, title="Renombrar Canal"):
    name_input = discord.ui.TextInput(label="Nuevo nombre", max_length=50)
    def __init__(self, member, voice_channel):
        super().__init__(); self.member = member; self.voice_channel = voice_channel
    async def on_submit(self, interaction: discord.Interaction):
        try: await self.voice_channel.edit(name=f"⛧︲{self.name_input.value}")
        except: pass
        await interaction.response.send_message(f"Renombrado por ⛧︲{self.name_input.value}", ephemeral=True)

class OwnerTransferView(discord.ui.View):
    def __init__(self, old_owner, voice_channel, members):
        super().__init__(timeout=300)
        self.old_owner = old_owner; self.voice_channel = voice_channel
        if members: self.add_item(NewOwnerSelect(old_owner, voice_channel, members))

class NewOwnerSelect(discord.ui.Select):
    def __init__(self, old_owner, voice_channel, members):
        self.old_owner = old_owner; self.voice_channel = voice_channel
        options = [discord.SelectOption(label=m.display_name, value=str(m.id)) for m in members[:25]]
        super().__init__(placeholder="Selecciona nuevo admin...", options=options)
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.old_owner.id: return
        new_id = int(self.values[0])
        new_owner = interaction.guild.get_member(new_id)
        if new_owner in self.voice_channel.members:
            data["voice_channel_owners"][str(self.voice_channel.id)] = new_id
            await create_voice_control_panel(new_owner, self.voice_channel, interaction.guild)
            task = f"{self.voice_channel.id}_{self.old_owner.id}"
            if task in data["owner_left_tasks"]: del data["owner_left_tasks"][task]
            save_data(data)
            await interaction.message.delete()
            await interaction.response.send_message(f"Admin cambiado a {new_owner.display_name}", ephemeral=True)

# --- COMANDOS ---

@bot.tree.command(name="invite", description="Genera invitación + key de acceso válida")
async def invite_cmd(interaction: discord.Interaction):
    if interaction.channel_id != PINNED_RESPONSE_CHANNEL_ID:
        await interaction.response.send_message(f"❌ Comando solo disponible en <#{PINNED_RESPONSE_CHANNEL_ID}>", ephemeral=True)
        return

    code = generate_code()
    data["codes"].append(code)
    save_data(data)
    
    try:
        invite = await interaction.channel.create_invite(max_uses=1, unique=True, max_age=86400) # 24h
    except Exception as e:
        await interaction.response.send_message(f"Error creando invite: {e}", ephemeral=True)
        return
        
    embed = discord.Embed(title="✦ INVITACIÓN CHEPA 2.0 ✦", color=0x2b2d31)
    embed.add_field(name="🔗 Link", value=f"[Click para entrar]({invite.url})", inline=False)
    embed.add_field(name="🔑 Key de Acceso", value=f"```fix\n{code}\n```", inline=False)
    embed.set_footer(text="Copia la Key. Te la pedirá el bot al entrar.")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="gen_keys", description="Generar keys manualmente (Admin)")
async def gen_keys(interaction: discord.Interaction, amount: int = 5):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
    new = [generate_code() for _ in range(amount)]
    data["codes"].extend(new)
    save_data(data)
    await interaction.response.send_message(f"Generadas:\n```\n" + "\n".join(new) + "\n```", ephemeral=True)

# --- EVENTOS ---

@bot.event
async def on_ready():
    if not DISCORD_TOKEN:
        print("❌ ERROR CRÍTICO: FALTA EL TOKEN EN EL ARCHIVO .ENV")
        return
        
    guild = bot.get_guild(GUILD_ID)
    if not guild: return print(f"❌ GUILD ID {GUILD_ID} NO ENCONTRADA")
    
    if not data.get("codes"):
        data["codes"] = [generate_code() for _ in range(10)]
        save_data(data)
        print("Códigos iniciales generados.")

    ch = guild.get_channel(LOGIN_CHANNEL_ID)
    if ch:
        try:
            async for m in ch.history(limit=50):
                if m.author == bot.user: await m.delete()
            embed = discord.Embed(
                title="🔐 ACCESO AL SISTEMA",
                description="Introduce tu **KEY DE ACCESO** abajo.\n\n⚠️ Tienes 3 intentos antes del bloqueo.",
                color=0x2b2d31
            )
            await ch.send(embed=embed)
        except: pass
        
    await cleanup_orphaned_channels(guild)
    print(f"🤖 BENDER IS READY en {guild.name}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.guild.id != GUILD_ID: return
    user_id = str(member.id)
    
    # 1. ENTRAR AL CREATOR
    if after.channel and after.channel.id == VOICE_CREATOR_ID:
        if user_id not in data["user_channels"]:
            try: await member.move_to(None)
            except: pass
            return

        if user_id not in voice_creation_locks: voice_creation_locks[user_id] = asyncio.Lock()
        async with voice_creation_locks[user_id]:
            if user_id in data.get("active_voice_channels", {}):
                ch = member.guild.get_channel(data["active_voice_channels"][user_id])
                if ch: return await member.move_to(ch)
                else: del data["active_voice_channels"][user_id]

            cat = after.channel.category
            overwrites = {
                member.guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                member: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=False, move_members=True)
            }
            lim_role = member.guild.get_role(LIMITED_ROLE_ID)
            if lim_role: overwrites[lim_role] = discord.PermissionOverwrite(connect=False, view_channel=False)

            try:
                vc = await member.guild.create_voice_channel(f"⛧︲{member.display_name}", category=cat, overwrites=overwrites)
                data["active_voice_channels"][user_id] = vc.id
                data["voice_channel_owners"][str(vc.id)] = member.id
                data["channel_modes"][str(vc.id)] = "public"
                data["member_join_times"].setdefault(str(vc.id), {})[user_id] = datetime.now().isoformat()
                save_data(data)
                
                await asyncio.sleep(0.5)
                await member.move_to(vc)
                await create_voice_control_panel(member, vc, member.guild)
            except Exception as e: print(f"Error creando canal: {e}")

    # 2. SALIR DE CANAL PERSONAL
    if before.channel and before.channel.id != VOICE_CREATOR_ID and before.channel.name.startswith("⛧︲"):
        cid_str = str(before.channel.id)
        is_owner = (data.get("voice_channel_owners", {}).get(cid_str) == member.id)
        left_count = len(before.channel.members)

        if is_owner and left_count > 0:
            await cleanup_pending_transfer(before.channel.id, member.guild)
            await handle_owner_left(before.channel, member.id, member.guild)
        
        elif left_count == 0:
            await cleanup_pending_transfer(before.channel.id, member.guild)
            if is_owner: await delete_control_message(member.id, member.guild)
            try: await before.channel.delete()
            except: pass
            
            owner_uid = next((u for u, c in data.get("active_voice_channels", {}).items() if c == before.channel.id), None)
            if owner_uid: del data["active_voice_channels"][owner_uid]
            for d in ["voice_channel_owners", "channel_modes", "crystal_permits", "member_join_times"]:
                if cid_str in data.get(d, {}): del data[d][cid_str]
            save_data(data)

    # 3. VOLVER A CANAL
    if after.channel and after.channel.id != VOICE_CREATOR_ID and after.channel.name.startswith("⛧︲"):
        cid_str = str(after.channel.id)
        task_id = f"{cid_str}_{member.id}"
        
        if task_id in data.get("owner_left_tasks", {}):
            data["voice_channel_owners"][cid_str] = member.id
            t_data = data["owner_left_tasks"][task_id]
            try:
                ch = member.guild.get_channel(t_data["temp_message_channel_id"])
                msg = await ch.fetch_message(t_data["temp_message_id"])
                await msg.delete()
            except: pass
            del data["owner_left_tasks"][task_id]
            save_data(data)
            await create_voice_control_panel(member, after.channel, member.guild)

@bot.event
async def on_member_join(member):
    if member.guild.id != GUILD_ID: return
    r = member.guild.get_role(LIMITED_ROLE_ID)
    if r: await member.add_roles(r)

@bot.event
async def on_message(message):
    if message.author.bot or message.guild.id != GUILD_ID: return

    # --- LOGIN SYSTEM ---
    if message.channel.id == LOGIN_CHANNEL_ID:
        uid = str(message.author.id)
        
        if uid in data["timeout_until"]:
            to = datetime.fromisoformat(data["timeout_until"][uid])
            if datetime.now() < to:
                await message.delete()
                await message.channel.send(f"⛔ {message.author.mention} Bloqueado temporalmente.", delete_after=5)
                return
            else:
                del data["timeout_until"][uid]
                data["failed_attempts"][uid] = 0
                save_data(data)

        code = message.content.strip()

        if code in data["codes"]:
            data["codes"].remove(code)
            if uid in data["failed_attempts"]: del data["failed_attempts"][uid]
            save_data(data)
            
            r = message.guild.get_role(LIMITED_ROLE_ID)
            if r and r in message.author.roles: 
                try: await message.author.remove_roles(r)
                except: pass
            
            try: await message.delete()
            except: pass
            
            new_ch = await create_self_channel(message.author, message.guild)
            await message.channel.send(f"✅ **ACCESO CONCEDIDO**\nBienvenido {message.author.mention}. Ve a tu terminal: {new_ch.mention}", delete_after=15)
        
        else:
            data["failed_attempts"][uid] = data.get("failed_attempts", {}).get(uid, 0) + 1
            att = data["failed_attempts"][uid]
            try: await message.delete()
            except: pass
            
            if att >= 3:
                data["timeout_until"][uid] = (datetime.now() + timedelta(hours=1)).isoformat()
                await message.channel.send(f"⛔ {message.author.mention} 3 Fallos. Bloqueado 1h.", delete_after=5)
            else:
                await message.channel.send(f"❌ Key inválida. ({att}/3)", delete_after=5)
            save_data(data)

    # --- IA CHAT ---
    elif message.channel.id == AI_CHANNEL_ID:
        async with message.channel.typing():
            try:
                txt = message.content
                if txt.lower().startswith(("busca ", "search ")):
                    res = await search_web(txt.split(" ", 1)[1])
                    txt = f"Data: {res}\nAnaliza."
                
                img_an = None
                if message.attachments:
                    for a in message.attachments:
                        if a.content_type and a.content_type.startswith('image/'):
                            img_an = await analyze_image(a.url, txt); break
                
                if img_an: reply = img_an
                else:
                    data["conversation_history"].append({"role": "user", "content": txt})
                    data["conversation_history"] = data["conversation_history"][-15:]
                    msgs = [{"role": "system", "content": SERVER_CONTEXT}] + data["conversation_history"]
                    response = openai.ChatCompletion.create(model=OPENAI_MODEL, messages=msgs, max_tokens=800)
                    reply = response['choices'][0]['message']['content']
                    data["conversation_history"].append({"role": "assistant", "content": reply})
                    save_data(data)
                
                for chunk in [reply[i:i+2000] for i in range(0, len(reply), 2000)]: await message.reply(chunk)
            except Exception as e: await message.reply(f"Error: {e}")

    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id: return
    uid = str(payload.user_id)
    if uid not in data["user_channels"]: return
    
    ud = data["user_channels"][uid]
    cid = ud["channel_id"] if isinstance(ud, dict) else ud
    mid = ud.get("color_msg_id") if isinstance(ud, dict) else None
    
    if payload.channel_id != cid or payload.message_id != mid: return
    
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    estr = str(payload.emoji)
    
    if estr not in EMOJI_TO_ROLE:
        try: await (await guild.get_channel(cid).fetch_message(mid)).remove_reaction(payload.emoji, member)
        except: pass
        return

    for e, rid in EMOJI_TO_ROLE.items():
        if e != estr:
            r = guild.get_role(rid)
            if r in member.roles: 
                try: await member.remove_roles(r)
                except: pass
    
    nr = guild.get_role(EMOJI_TO_ROLE[estr])
    if nr:
        await member.add_roles(nr)
        msg = await guild.get_channel(cid).fetch_message(mid)
        emb = msg.embeds[0]
        emb.set_field_at(0, name="╔═══ IDENTIDAD ACTUAL ═══╗", value=f"```fix\n{estr} {nr.name} ACTIVO\n```", inline=False)
        await msg.edit(embed=emb)
        
        for r in msg.reactions:
            if str(r.emoji) != estr: 
                try: await r.remove(member)
                except: pass

@bot.event
async def on_raw_reaction_remove(payload): pass

if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("Por favor configura el archivo .env primero")
