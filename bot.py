#!/usr/bin/env python3
"""
bot.py - Unified Discord bot:
 - Monika AI (Gemini REST async + fallback + short-term memory)
 - Minigames: Hangman, Trivia, RPS, CoinFlip, Scramble, MathQuiz
 - Chess: python-chess, modal nhập nước, Monika đi nước bằng heuristic
 - Health server (aiohttp) để Render detect PORT (optional)
USAGE:
 - Set environment variables DISCORD_BOT_TOKEN (required) and optionally GEMINI_API_KEY.
 - requirements.txt provided separately.
"""
import os
import random
import asyncio
import traceback
from typing import Optional, Tuple, List
from collections import deque

import discord
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web, ClientSession, ClientTimeout

# Optional: python-chess (required for chess feature)
try:
    import chess
    CHESS_AVAILABLE = True
except Exception:
    CHESS_AVAILABLE = False

# Load local .env for dev only
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not DISCORD_TOKEN:
    print("ERROR: Missing DISCORD_BOT_TOKEN environment variable.")
    raise SystemExit(1)

# ---------------- Monika AI Engine (REST async + fallback + anti-repeat) ----------------
class MonikaAIEngine:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.enabled = bool(api_key)
        self.session: Optional[ClientSession] = None
        self.recent_replies: dict[int, deque] = {}  # per-user recent replies

        # persona & few-shot helpers
        self.system_instruction = (
            "Bạn là Monika: dịu dàng, sâu sắc, thân mật nhưng lịch sự. Trả lời bằng tiếng Việt, "
            "ngắn gọn (1-3 câu), giàu cảm xúc và ân cần. Tránh nội dung NSFW và bạo lực."
        )
        self.fallback_openings = ["Mmm...", "Ồ...", "Ừm...", "Hehe...", "Aha..."]
        self.fallback_mids = ["mình thích điều đó", "mình muốn nghe thêm", "mình cảm thấy nhẹ nhàng", "cậu làm mình mỉm cười"]
        self.fallback_endings = ["kể thêm cho mình nhé.", "mình ở đây để nghe cậu.", "đừng giấu nhé."]

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            timeout = ClientTimeout(total=30)
            self.session = ClientSession(timeout=timeout)

    async def generate_response(self, user_message: str, user_id: Optional[int] = None) -> str:
        # Try REST call if key present
        if self.enabled:
            try:
                await self._ensure_session()
                url = f"https://generative.googleapis.com/v1/models/{self.model}:generate"
                prompt_text = f"{self.system_instruction}\n\nNgười dùng: {user_message}\nMonika:"
                body = {
                    "prompt": { "text": prompt_text },
                    "temperature": 0.75,
                    "maxOutputTokens": 300
                }
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                async with self.session.post(url, json=body, headers=headers) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        # log and fall back
                        print("Generative API returned", resp.status, text)
                        raise RuntimeError("Generative API error")
                    data = await resp.json()
                # extract text from common shapes
                candidate = None
                if isinstance(data, dict):
                    cand = data.get("candidates") or data.get("candidate")
                    if cand and isinstance(cand, list) and len(cand) > 0:
                        first = cand[0]
                        if isinstance(first, dict):
                            for k in ("content", "output", "text"):
                                if k in first and isinstance(first[k], str):
                                    candidate = first[k]
                                    break
                            if not candidate and "message" in first and isinstance(first["message"], dict):
                                msg = first["message"].get("content")
                                if isinstance(msg, str):
                                    candidate = msg
                        elif isinstance(first, str):
                            candidate = first
                    if not candidate and "output" in data:
                        out = data["output"]
                        if isinstance(out, list) and out:
                            f = out[0]
                            if isinstance(f, dict):
                                c = f.get("content")
                                if isinstance(c, str):
                                    candidate = c
                            elif isinstance(f, str):
                                candidate = f
                    if not candidate and "text" in data and isinstance(data["text"], str):
                        candidate = data["text"]
                if not candidate:
                    candidate = str(data)[:1000]
                return self._postprocess(candidate.strip(), user_id)
            except Exception as e:
                print("Gen API failed:", e)
                print(traceback.format_exc())
        # fallback
        return self._simulated_reply(user_message, user_id)

    def _postprocess(self, reply: str, user_id: Optional[int]) -> str:
        clean = reply.strip()
        if user_id is not None:
            dq = self.recent_replies.setdefault(user_id, deque(maxlen=6))
            if any(self._is_similar(clean, prev) for prev in dq):
                clean = clean + " " + random.choice(self.fallback_endings)
            dq.append(clean)
        return clean

    def _

