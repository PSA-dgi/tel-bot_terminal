import os
import shlex
import asyncio
from typing import List
import html
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import resource


TOKEN = "BOT-TOKEN"
ALLOWED_USERS: List[int] = [
    #example: 123456789
    ]

MAX_OUTPUT_BYTES = 16000
COMMAND_TIMEOUT = 10
SHELL_MODE = True  
ALLOW_MULTILINE_AS_BATCH = False
USE_LINUX_RESOURCE_LIMITS = True


user_cwd = {}


def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_USERS

def linux_preexec():
    try:
        
        resource.setrlimit(resource.RLIMIT_CPU, (COMMAND_TIMEOUT + 1, COMMAND_TIMEOUT + 1))
        resource.setrlimit(resource.RLIMIT_AS, (200 * 1024 * 1024, 200 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except Exception:
        pass

async def run_command(command: str, cwd: str) -> dict:
    is_windows = os.name == "nt"
    result = {"returncode": None, "stdout": b"", "stderr": b"", "timed_out": False, "error": None}

    if SHELL_MODE:
        args = ["cmd", "/c", command] if is_windows else ["bash", "-lc", command]
        use_shell = False
    else:
        try:
            args = shlex.split(command, posix=not is_windows)
        except Exception:
            args = ["cmd", "/c", command] if is_windows else ["bash", "-lc", command]
        use_shell = False

    try:
        preexec_fn = linux_preexec if (not is_windows and USE_LINUX_RESOURCE_LIMITS) else None
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=use_shell,
            preexec_fn=preexec_fn,
            cwd=cwd
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=COMMAND_TIMEOUT)
            result.update(returncode=proc.returncode, stdout=stdout or b"", stderr=stderr or b"")
        except asyncio.TimeoutError:
            result["timed_out"] = True
            proc.kill()
            stdout, stderr = await proc.communicate()
            result.update(returncode=-1, stdout=stdout or b"", stderr=stderr or b"")
    except Exception as e:
        result["error"] = str(e)

    return result


async def handle_command_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_allowed(user.id):
        return

    command = update.message.text.strip()
    if not command:
        return


    cwd = user_cwd.get(user.id, os.getcwd())


    if command.lower().startswith("cd "):
        path = command[3:].strip().replace("\\", "/")
        new_dir = os.path.abspath(os.path.join(cwd, path))
        if os.path.isdir(new_dir):
            user_cwd[user.id] = new_dir
            await update.message.reply_text(f"Changed directory to {new_dir}")
        else:
            await update.message.reply_text(f"Directory does not exist: {new_dir}")
        return


    res = await run_command(command, cwd)
    if res.get("error"):
        await update.message.reply_text(f"Error: {res['error']}")
        return

    output = format_output_bytes(res["stdout"], res["stderr"])
    footer = f"\n\nExit code: {res['returncode']}"
    if res["timed_out"]:
        footer += " (timed out)"

    for chunk in [output[i:i+3800] for i in range(0, len(output), 3800)]:
        safe_chunk = html.escape(chunk)
        await update.message.reply_text(f"<pre>{safe_chunk}</pre>", parse_mode="HTML")
    await update.message.reply_text(footer)



def format_output_bytes(stdout: bytes, stderr: bytes) -> str:
    combined = b""
    if stdout:
        combined += b"STDOUT:\n" + stdout
    if stderr:
        combined += b"\nSTDERR:\n" + stderr
    if len(combined) > MAX_OUTPUT_BYTES:
        half = MAX_OUTPUT_BYTES // 2
        combined = combined[:half] + b"\n...[truncated]...\n" + combined[-half:]
    return combined.decode(errors="replace")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text(
        "Shell bot ready.\nUse /r <command>"
    )

# async def run_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user = update.effective_user
#     if not is_allowed(user.id):
#         await update.message.reply_text("Unauthorized.")
#         return

#     command = " ".join(context.args) if context.args else None
#     if not command:
#         await update.message.reply_text("Usage: /run <command>")
#         return


#     cwd = user_cwd.get(user.id, os.getcwd())


#     if command.strip().lower().startswith("cd "):
#         path = command.strip()[3:].strip().replace("\\", "/")
#         new_dir = os.path.abspath(os.path.join(cwd, path))
#         if os.path.isdir(new_dir):
#             user_cwd[user.id] = new_dir
#             await update.message.reply_text(f"Changed directory to {new_dir}")
#         else:
#             await update.message.reply_text(f"Directory does not exist: {new_dir}")
#         return


#     res = await run_command(command, cwd)
#     if res.get("error"):
#         await update.message.reply_text(f"Error: {res['error']}")
#         return

#     output = format_output_bytes(res["stdout"], res["stderr"])
#     footer = f"\n\nExit code: {res['returncode']}"
#     if res["timed_out"]:
#         footer += " (timed out)"

#     for chunk in [output[i:i+3800] for i in range(0, len(output), 3800)]:
#         safe_chunk = html.escape(chunk)
#         await update.message.reply_text(f"<pre>{safe_chunk}</pre>", parse_mode="HTML")
#     await update.message.reply_text(footer)


def main():
    import asyncio
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    #app.add_handler(CommandHandler("run", run_cmd)) """FOR RUN COMMANDS WITH /run PREFIX"""   

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_command_message))  #"""FOR RUN COMMANDS DIRECTLY AS MESSAGES"""


    print("Bot is running. Press Ctrl+C to stop.")
    asyncio.run(app.run_polling())

if __name__ == "__main__":
    main()
