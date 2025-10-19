"""
AI Telegram Bot (OpenRouter)
Features:
- /start, /help menu
- AI chat via OpenRouter API (OPENROUTER_API_KEY in .env)
- /pdf: collect sent images and convert to multi-page PDF
- /readpdf: extract text from uploaded PDF (requires PyMuPDF)
- /style <disney|pixar|anime>: next image will be stylized (requires HF or other image model)
- /clear: clear user session
- /contact_admin: forward message to admin (ADMIN_ID in .env or default)
Note: Place your tokens in a .env file (see .env.example). Do NOT commit real keys to public repos.
"""

import os
import io
import logging
import base64
import requests
from typing import List, Dict

from telegram import Update, InputFile, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)
from dotenv import load_dotenv
from PIL import Image
import img2pdf

# Load env
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5255121773"))
TEMP_DIR = os.getenv("TEMP_DIR", "temp_files")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env")

os.makedirs(TEMP_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory admin reply map and known users
admin_reply_map: Dict[int, int] = {}
# app-level set is stored in application.chat_data['known_users']

# ---------------- OpenRouter helper ----------------
def openrouter_chat(prompt: str) -> str:
    """
    Send prompt to OpenRouter (simple HTTP call).
    Expects OPENROUTER_API_KEY in env.
    """
    if not OPENROUTER_API_KEY:
        return "(OpenRouter key missing) Fallback echo: " + prompt
    url = "https://api.openrouter.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    payload = {
        "model": "o4-mini",  # change if you prefer another OpenRouter model
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 800
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        # typical structure: data.choices[0].message.content
        if "choices" in data and data["choices"]:
            return data["choices"][0]["message"]["content"].strip()
        # fallback
        return str(data)[:1000]
    except Exception as e:
        logger.exception("OpenRouter request failed")
        return f"(OpenRouter error) {e}"

# ---------------- Image stylize helper (placeholder) ----------------
def stylize_image_bytes(image_bytes: bytes, style: str) -> bytes:
    """
    Placeholder stylize function. If you integrate a real model (HF, Replicate, etc.),
    implement it here. For now it returns the original image bytes.
    """
    # TODO: call HF/Replicate/OpenRouter image endpoints if available
    return image_bytes

# ---------------- PDF helpers ----------------
def images_to_pdf_bytes(image_paths: List[str]) -> bytes:
    try:
        return img2pdf.convert(image_paths)
    except Exception:
        # fallback using PIL
        buf = io.BytesIO()
        imgs = [Image.open(p).convert("RGB") for p in image_paths]
        imgs[0].save(buf, format="PDF", save_all=True, append_images=imgs[1:])
        return buf.getvalue()

def extract_text_from_pdf(path: str) -> str:
    try:
        import fitz
        doc = fitz.open(path)
        pages = [p.get_text() for p in doc]
        return "\n\n".join(pages).strip() or "No text found."
    except Exception as e:
        logger.exception("PDF text extraction failed")
        return "PDF text extraction requires PyMuPDF (fitz). Install it for better results."

# ---------------- Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["/chat", "/style"],
        ["/pdf", "/readpdf"],
        ["/contact_admin", "/help"],
    ]
    text = (
        "👋 *Salom!* Men OpenRouter orqali ishlovchi AI-botman.\n\n"
        "Quyidagi buyruqlar mavjud:\n"
        "🗣 /chat — AI bilan suhbat (matn yuboring)\n"
        "🎨 /style <disney|pixar|anime> — keyin rasm yuboring, rasm shu uslubda qayta ishlanadi\n"
        "📄 /pdf — rasm yuboring (yoki bir nechta), so‘ng /pdf bilan barchasini PDFga aylantiring\n"
        "📖 /readpdf — PDF yuboring, men ichidan matn ajratib beraman\n"
        "🧹 /clear — sessiya va vaqtinchalik fayllarni tozalash\n"
        "📩 /contact_admin — admin bilan bog'lanish\n"
    )
    await update.message.reply_markdown(text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Yordam: /start — menyu. /contact_admin orqali admin bilan bog'laning.")

async def chat_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text.strip()
    await update.message.chat.action("typing")
    reply = openrouter_chat(prompt)
    await update.message.reply_text(reply)

async def cmd_chat_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Endi menga matn yuboring — men OpenRouter orqali javob beraman.")

# Photo handler: collects images and optionally stylizes
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photos = update.message.photo
    if not photos:
        await update.message.reply_text("Rasm topilmadi.")
        return
    user = update.message.from_user
    file = await photos[-1].get_file()
    user_dir = os.path.join(TEMP_DIR, str(user.id))
    os.makedirs(user_dir, exist_ok=True)
    idx = len([n for n in os.listdir(user_dir) if n.lower().endswith(('.jpg','.png'))])
    path = os.path.join(user_dir, f"img_{idx+1}.jpg")
    await file.download_to_drive(path)

    style = context.user_data.get("style")
    if style:
        await update.message.reply_text(f"Rasm qabul qilindi — {style} uslubida qayta ishlanmoqda...")
        with open(path, "rb") as f:
            orig = f.read()
        out = stylize_image_bytes(orig, style)
        await update.message.reply_photo(photo=io.BytesIO(out), caption=f"{style.title()} uslubida")
        # save stylized image to collection
        styl_path = os.path.join(user_dir, f"styl_{idx+1}.jpg")
        with open(styl_path, "wb") as f:
            f.write(out)
        images = context.user_data.setdefault("images", [])
        images.append(styl_path)
        context.user_data.pop("style", None)
        return

    images = context.user_data.setdefault("images", [])
    images.append(path)
    await update.message.reply_text("✅ Rasm saqlandi. Bir nechta rasm yuboring, so‘ng /pdf bilan PDF oling.")

async def cmd_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    images = context.user_data.get("images")
    if not images:
        await update.message.reply_text("Hech qanday rasm topilmadi. Iltimos rasm yuboring.")
        return
    pdf_bytes = images_to_pdf_bytes(images)
    await update.message.reply_document(InputFile(io.BytesIO(pdf_bytes), filename="images.pdf"))
    context.user_data["images"] = []

async def cmd_readpdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("Iltimos PDF yuboring.")
        return
    file = await update.message.document.get_file()
    user = update.message.from_user
    user_dir = os.path.join(TEMP_DIR, str(user.id))
    os.makedirs(user_dir, exist_ok=True)
    pdf_path = os.path.join(user_dir, "incoming.pdf")
    await file.download_to_drive(pdf_path)
    text = extract_text_from_pdf(pdf_path)
    if len(text) > 3000:
        txt_path = os.path.join(user_dir, "extracted.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
        await update.message.reply_document(InputFile(txt_path), filename="extracted.txt")
    else:
        await update.message.reply_text(text)

async def cmd_style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Masalan: /style disney yoki /style anime")
        return
    style = parts[1].lower()
    if style not in {"disney","pixar","anime"}:
        await update.message.reply_text("Faqat disney, pixar yoki anime qabul qilinadi.")
        return
    context.user_data["style"] = style
    await update.message.reply_text(f"{style.title()} uslubi tanlandi. Iltimos rasm yuboring.")

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    user_dir = os.path.join(TEMP_DIR, uid)
    if os.path.isdir(user_dir):
        for f in os.listdir(user_dir):
            try:
                os.remove(os.path.join(user_dir, f))
            except Exception:
                pass
    context.user_data.clear()
    await update.message.reply_text("Sessiyangiz tozalandi.")

async def cmd_contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_admin_msg"] = True
    await update.message.reply_text("Adminga yuboriladigan xabarni yozing:")

async def handle_admin_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_admin_msg"):
        return False
    text = update.message.text or ""
    user = update.message.from_user
    msg = (
        f"📩 *Xabar adminga*\n\n"
        f"Foydalanuvchi: {user.full_name} (id: {user.id})\n"
        f"Username: @{user.username or '—'}\n\n"
        f"Xabar:\n{text}"
    )
    sent = await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
    admin_reply_map[sent.message_id] = user.id
    context.user_data.pop("awaiting_admin_msg", None)
    await update.message.reply_text("✅ Xabaringiz adminga yuborildi.")
    return True

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply qilib admin xabarini yuboring.")
        return
    replied_id = update.message.reply_to_message.message_id
    target = admin_reply_map.get(replied_id)
    if not target:
        await update.message.reply_text("Mos foydalanuvchi topilmadi.")
        return
    if update.message.photo:
        await context.bot.send_photo(chat_id=target, photo=update.message.photo[-1].file_id, caption=update.message.caption or "Admin javobi")
    elif update.message.text:
        await context.bot.send_message(chat_id=target, text=f"📬 Admindan javob:\n\n{update.message.text}")
    await update.message.reply_text("Javob foydalanuvchiga yuborildi.")

# broadcast simple
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("Bu buyruq faqat admin uchun.")
        return
    known = context.application.chat_data.setdefault("known_users", set())
    if not known:
        await update.message.reply_text("Hech qanday foydalanuvchi ro'yxati yo'q.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply qilib /broadcast yozing.")
        return
    sent = 0
    for uid in list(known):
        try:
            if update.message.reply_to_message.text:
                await context.bot.send_message(chat_id=uid, text=f"[Admin broadcast]\n\n{update.message.reply_to_message.text}")
            elif update.message.reply_to_message.photo:
                await context.bot.send_photo(chat_id=uid, photo=update.message.reply_to_message.photo[-1].file_id, caption="[Admin broadcast]")
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"Broadcast jo'natildi: taxminan {sent} ta.")

async def track_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    known = context.application.chat_data.setdefault("known_users", set())
    if uid not in known:
        known.add(uid)

# text router
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_user(update, context)
    if update.message.from_user.id == ADMIN_ID and update.message.reply_to_message:
        await handle_admin_reply(update, context)
        return
    if context.user_data.get("awaiting_admin_msg"):
        handled = await handle_admin_forward(update, context)
        if handled:
            return
    # normal chat
    await chat_text(update, context)

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("chat", cmd_chat_prompt))
    app.add_handler(CommandHandler("pdf", cmd_pdf))
    app.add_handler(CommandHandler("readpdf", cmd_readpdf))
    app.add_handler(CommandHandler("style", cmd_style))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("contact_admin", cmd_contact_admin))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    app.add_handler(MessageHandler(filters.Document.MIME_TYPE("application/pdf"), cmd_readpdf))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    logger.info("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
