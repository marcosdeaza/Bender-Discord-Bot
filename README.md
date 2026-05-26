# ⛧ BENDER — Discord AutoManaging Bot (IA + Verificación + Self-Spaces)
![Bender Smoking](https://images.fineartamerica.com/images/artworkimages/medium/3/smoking-bender-futurama-diah-kezia-yuniar-transparent.png)

> “Bienvenido a tu servidor. Ahora todo se gestiona solo.”
>
> **BENDER** es un bot de *automanaging* para Discord que crea un **entorno completo** dentro del servidor:
- **Verificación por Key / invitación**
- **IA integrada con OpenAI** (chat + análisis de imágenes)
- **Espacios privados por usuario (“self terminals”)**
- **Roles por reacciones (colores/identidad)**
- **Creación automática de canales de voz** + panel de control (Público / Ghost / Crystal)
- **Transferencia de ownership** y limpieza automática
- Diseño enfocado en **descentralizar poder** y reducir **admin abuse**.

---

## ✦ Filosofía: Anti-Admin-Abuse / “Confort Descentralizado”
Este bot implementa un patrón de servidor donde cada usuario tiene:
- Su **mini-espacio privado** (`⛧︲self`) con paneles y controles.
- Canales de voz “personales” que se crean al entrar a un **Voice Creator**.
- Controles accesibles **al dueño del canal** (no al staff), reduciendo la necesidad de moderación manual.

---

## ✅ Features (lo que hace de verdad)

### 1) 🔐 Sistema de verificación por KEY (Login Gate)
**Objetivo:** evitar raids / accesos no autorizados.
- A todo usuario que entra se le asigna un rol **LIMITED**.
- Debe escribir una **KEY** en el canal de login (`LOGIN_CHANNEL_ID`).
- Tiene **3 intentos**:
  - Si falla 3 veces → **timeout 1 hora**
- Si acierta:
  - Se consume la key (one-time use).
  - Se le quita el rol LIMITED.
  - Se crea su canal privado `⛧︲self`.

**Comandos:**
- `/invite` → genera **invite de 1 uso** + **key válida** (solo permitido en canal “pinned_response”).
- `/gen_keys amount` → genera keys manualmente (solo admin).

---

### 2) 🧠 IA integrada (OpenAI) + búsqueda web básica
En el canal de IA (`AI_CHANNEL_ID`):
- Conversación con contexto de sistema (**Bender persona**) + **historial persistente** (últimos 15 mensajes).
- Si el usuario escribe:
  - `busca <query>` / `search <query>` → llama a DuckDuckGo API (resumen + related topics) y luego pide análisis a la IA.
- Si el mensaje trae **imagen adjunta**, se ejecuta **análisis de imagen** (modelo multimodal).

---

### 3) 🧿 “Self Terminal” privado por usuario
Al verificarse, se crea `⛧︲self`:
- Solo el usuario puede leer.
- El bot puede escribir.
- El usuario **no puede spamear** (send_messages=False), pensado como “panel/terminal” de configuración personal.

Dentro se envía un embed con:
- **Selección de identidad** (roles) reaccionando con emojis.
- Solo una identidad activa a la vez.
- El embed se actualiza automáticamente al cambiar.

---

### 4) 🎭 Roles por reacciones (Identidad/Color)
El bot mantiene una tabla `EMOJI → ROLE_ID`.
- Al reaccionar a tu panel en `⛧︲self`:
  - Remueve roles anteriores de la categoría.
  - Asigna el rol elegido.
  - Actualiza el embed con el rol activo.
  - Limpia reacciones restantes para que quede solo la elegida.

---

### 5) 🔊 Canales de voz auto-creados + “Voice Creator”
Cuando un usuario entra al canal `VOICE_CREATOR_ID`:
- Si NO está verificado (sin `self`) → **se le expulsa del voice**.
- Si está verificado:
  - Se crea un canal nuevo: `⛧︲<nombre>`
  - Se mueve al usuario automáticamente
  - Se registra como **owner** del canal
  - Se postea un panel de control en su `⛧︲self`

**Si el usuario ya tenía un canal activo**, se lo reusa (y se le mueve ahí).

---

### 6) 🎛 Panel de control del canal de voz (Botones + UI)
El dueño del canal tiene un panel con:
- **Modo** (cíclico): `PÚBLICO → GHOST → CRYSTAL → PÚBLICO`
- **Kick** (selector de usuarios presentes)
- **Renombrar** canal (modal)

#### Modos de privacidad
- **PÚBLICO (🌍)**  
  - `@everyone` puede ver y conectar.
  - `LIMITED` sigue bloqueado.

- **GHOST (👻) — Invisible**
  - `@everyone` no ve ni conecta.
  - Solo owner + bot + whitelist.

- **CRYSTAL (🔮) — Visible pero privado**
  - En tu implementación actual, Crystal usa la misma base “privada” que Ghost: bloquea `@everyone` y permite solo whitelist.
  - Incluye **selector** para añadir/quitar usuarios permitidos (whitelist dinámica).

✅ **Auto-whitelist inteligente:**  
Cuando cambias a un modo privado (Ghost/Crystal), el bot guarda automáticamente a los usuarios que ya estaban dentro para que **no los expulse** por el cambio de modo.

---

### 7) 🔁 Transferencia de ownership (si el dueño se va)
Si el owner sale del canal y aún queda gente dentro:
- Se abre un proceso de **transferencia** con ventana de **5 minutos**.
- Se publica un mensaje con selector (en el `⛧︲self` del owner) para elegir nuevo admin.
- Si el owner vuelve antes del timeout → recupera control.
- Si no se elige a nadie:
  - Si queda alguien, el primero se vuelve owner.
  - Si no queda nadie → el canal se elimina.

---

### 8) 🧹 Limpieza automática / anti-bug
En `on_ready()`:
- Limpia mensajes previos del canal login (hasta 50) y reposta el embed de acceso.
- Ejecuta `cleanup_orphaned_channels()`:
  - Borra canales `⛧︲` vacíos (excepto el creator).
  - Resetea estructuras de tracking para evitar estados corruptos.

---

## 🧱 Arquitectura (alto nivel)

### Persistencia
Se guarda todo en `bender_data.json`:
- Keys disponibles
- Canales self por usuario
- Historial conversación IA
- Estado de canales de voz creados
- Owners, modos, whitelist “crystal”
- Intentos fallidos + timeouts
- Tareas de transferencia pendientes

> Esto permite reiniciar el bot sin perder el estado crítico.

### Flujo principal
1. Usuario entra → rol LIMITED
2. Usuario manda KEY → se verifica
3. Se crea `⛧︲self` + panel identidad (roles)
4. Usuario entra a Voice Creator → se crea canal de voz personal
5. Panel de control en `⛧︲self` gestiona privacidad / kick / rename
6. Al vaciarse el canal → se borra solo

---

## ⚙️ Setup

### Requisitos
- Python 3.10+ recomendado
- `discord.py` con `app_commands` habilitado
- `aiohttp`
- SDK de OpenAI (compatible con tu llamada `openai.ChatCompletion.create`)

### Instalación
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install -U discord.py aiohttp openai
