import os
import re
import math
import asyncio
import hashlib
import random
import subprocess
import requests
from telethon import TelegramClient
from telethon.tl.functions.upload import SaveBigFilePartRequest
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import (
    InputFileBig,
    InputMediaUploadedDocument,
    DocumentAttributeFilename,
)

# ====== YOUR API DETAILS ======
api_id   = 38963550
api_hash = "1e7e73506dd3e91f2c513240e701945d"
phone    = "+94704608828"
# ==============================

PART_SIZE    = 1990 * 1024 * 1024
UPLOAD_CHUNK = 512 * 1024
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

MAX_RETRIES  = 5
CHUNK_SIZE   = 4 * 1024 * 1024


# ═══════════════════════════════════════════
#  MD5 CHECKSUM
# ═══════════════════════════════════════════
def md5_file(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ═══════════════════════════════════════════
#  YOUTUBE DOWNLOADER (yt-dlp)
# ═══════════════════════════════════════════
def check_ytdlp():
    """yt-dlp install wela thiyanawada check karanawa"""
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[!] yt-dlp nemata. Install karanawa...")
        subprocess.run(["pip", "install", "-U", "yt-dlp"], check=True)
        return True


def get_youtube_formats(url: str):
    """Available formats list karanawa"""
    result = subprocess.run(
        ["yt-dlp", "-F", url],
        capture_output=True, text=True
    )
    print(result.stdout)


def download_youtube(url: str, quality: str = "best") -> str:
    """
    YouTube video full quality download karanawa.
    quality options:
        "best"   - Best video + audio (merged)
        "4k"     - 2160p
        "1080p"  - 1080p
        "720p"   - 720p
        "audio"  - Audio only (mp3)
    """
    check_ytdlp()

    # Format selection
    format_map = {
        "best" : "bestvideo+bestaudio/best",
        "4k"   : "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p" : "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "audio": "bestaudio/best",
    }

    fmt = format_map.get(quality, "bestvideo+bestaudio/best")

    # Output filename
    output_template = "%(title)s.%(ext)s"

    cmd = [
        "yt-dlp",
        "-f", fmt,
        "--merge-output-format", "mp4",   # Always mp4 output
        "--output", output_template,
        "--progress",
        "--no-playlist",                   # Single video only (playlist disable)
        "--cookies-from-browser", "chrome",  # YouTube age restrict bypass
        url
    ]

    # Audio only nam mp3 convert
    if quality == "audio":
        cmd = [
            "yt-dlp",
            "-f", "bestaudio/best",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--output", output_template,
            "--progress",
            url
        ]

    print(f"\n[*] Quality: {quality}")
    print(f"[*] Format : {fmt}")
    print(f"[↓] Downloading YouTube video...\n")

    # Get video title first (filename find karanata)
    title_result = subprocess.run(
        ["yt-dlp", "--get-filename", "-o", output_template, "-f", fmt,
         "--merge-output-format", "mp4", url],
        capture_output=True, text=True
    )
    expected_filename = title_result.stdout.strip()
    print(f"[*] Expected file: {expected_filename}")

    # Download
    result = subprocess.run(cmd)

    if result.returncode != 0:
        raise Exception("YouTube download failed! URL check karanawa.")

    # Find downloaded file
    if os.path.exists(expected_filename):
        actual_size = os.path.getsize(expected_filename)
        print(f"\n[✓] Download complete: {expected_filename}")
        print(f"[*] Size: {actual_size // (1024**2)} MB")
        return expected_filename
    else:
        # Search for recently created mp4 file
        files = [f for f in os.listdir(".") if f.endswith((".mp4", ".mkv", ".mp3", ".webm"))]
        if files:
            latest = max(files, key=os.path.getmtime)
            print(f"[✓] Found: {latest}")
            return latest
        raise Exception("Downloaded file nemata!")


# ═══════════════════════════════════════════
#  GOFILE DOWNLOADER (original)
# ═══════════════════════════════════════════
def get_website_token() -> str:
    try:
        resp = requests.get(
            "https://gofile.io/dist/js/config.js",
            headers={"User-Agent": UA}, timeout=15
        )
        resp.raise_for_status()
        js = resp.text

        if 'appdata.wt = "' in js:
            tok = js.split('appdata.wt = "')[1].split('"')[0]
            print(f"[*] WebsiteToken: {tok}")
            return tok

        for pat in [
            r'websiteToken["\']?\s*[=:]\s*["\']([^"\']{4,})["\']',
            r'"wt"\s*:\s*"([^"]{4,})"',
        ]:
            m = re.search(pat, js)
            if m:
                return m.group(1)

        raise Exception(f"Token nemata:\n{js[:400]}")
    except Exception as e:
        raise Exception(f"config.js fail: {e}")


def get_gofile_direct_link(page_url: str):
    if "/d/" not in page_url:
        raise ValueError("Valid GoFile link: https://gofile.io/d/XXXXX")

    content_id = page_url.rstrip("/").split("/d/")[-1]
    print(f"[*] Content ID : {content_id}")

    r = requests.post(
        "https://api.gofile.io/accounts",
        headers={"User-Agent": UA}, timeout=15
    ).json()
    if r.get("status") != "ok":
        raise Exception(f"Guest token fail: {r}")
    guest_token = r["data"]["token"]

    wt = get_website_token()
    headers = {
        "Authorization": f"Bearer {guest_token}",
        "X-Website-Token": wt,
        "User-Agent": UA,
    }

    resp = requests.get(
        f"https://api.gofile.io/contents/{content_id}?cache=true",
        headers=headers, timeout=30
    ).json()

    if resp.get("status") != "ok":
        err = resp.get("status", "?")
        tips = {
            "error-notPremium": "X-Website-Token wrong/expired.",
            "error-notFound"  : "Content ID invalid.",
            "error-passwordRequired": "Password protected.",
        }
        raise Exception(f"GoFile error: {err} — {tips.get(err, '')}")

    data     = resp["data"]
    children = data.get("children", {})
    file_item = next((v for v in children.values() if v.get("type") == "file"), None)
    if not file_item:
        file_item = data if data.get("type") == "file" else None
    if not file_item:
        raise Exception("File nemata.")

    name     = file_item["name"]
    url      = file_item["link"]
    size     = file_item.get("size", 0)
    md5      = file_item.get("md5", None)

    print(f"[*] File  : {name}")
    print(f"[*] Size  : {size // (1024**2)} MB")
    if md5:
        print(f"[*] MD5   : {md5}  (server provided)")

    return url, name, headers, md5


def download_file(url: str, filename: str, headers: dict, expected_md5: str = None):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"\n[↓] Download attempt {attempt}/{MAX_RETRIES}: {filename}")

            downloaded = 0
            if os.path.exists(filename):
                downloaded = os.path.getsize(filename)
                if downloaded > 0:
                    print(f"    Resuming from {downloaded // (1024**2)} MB...")

            req_headers = dict(headers)
            if downloaded > 0:
                req_headers["Range"] = f"bytes={downloaded}-"

            with requests.get(url, headers=req_headers, stream=True, timeout=60) as r:
                if r.status_code == 416:
                    print("    Already fully downloaded.")
                    break

                r.raise_for_status()

                total = int(r.headers.get("content-length", 0)) + downloaded
                mode  = "ab" if downloaded > 0 else "wb"
                hasher = hashlib.md5()

                if downloaded > 0 and os.path.exists(filename):
                    print("    Hashing existing data...")
                    with open(filename, "rb") as existing:
                        while True:
                            c = existing.read(8 * 1024 * 1024)
                            if not c:
                                break
                            hasher.update(c)

                done = downloaded
                with open(filename, mode) as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        f.write(chunk)
                        f.flush()
                        os.fsync(f.fileno())
                        hasher.update(chunk)
                        done += len(chunk)

                        if total:
                            pct = done / total * 100
                            print(
                                f"\r    {pct:5.1f}%  {done//(1024**2)}MB / {total//(1024**2)}MB",
                                end="", flush=True
                            )

            print(f"\n[✓] Download complete: {done//(1024**2)} MB")

            actual_size = os.path.getsize(filename)
            if total and actual_size != total:
                raise Exception(f"Size mismatch! Expected {total} bytes, got {actual_size} bytes.")

            local_md5 = hasher.hexdigest()
            print(f"[*] Local MD5  : {local_md5}")

            if expected_md5:
                if local_md5.lower() == expected_md5.lower():
                    print("[✓] MD5 match — file intact!")
                else:
                    raise Exception(
                        f"MD5 MISMATCH!\n  Expected : {expected_md5}\n  Got      : {local_md5}"
                    )
            else:
                print("[*] Server MD5 nemata — size verify only.")

            return local_md5

        except Exception as e:
            print(f"\n[!] Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                wait = 5 * attempt
                print(f"    {wait}s wait karala retry karanawa...")
                import time; time.sleep(wait)
                if os.path.exists(filename) and "MD5 MISMATCH" in str(e):
                    os.remove(filename)
            else:
                raise Exception(f"Download failed after {MAX_RETRIES} attempts: {e}")


# ═══════════════════════════════════════════
#  FILE SPLITTER
# ═══════════════════════════════════════════
def split_file(path: str) -> list:
    size = os.path.getsize(path)
    n    = math.ceil(size / PART_SIZE)
    print(f"\n[*] File size : {size/(1024**3):.3f} GB")
    print(f"[*] Parts     : {n} x ~{PART_SIZE//(1024**2)} MB")

    if n == 1:
        print("[*] Split karanna oni naha.")
        return [path]

    parts = []
    print("[*] Original file MD5 calculating...")
    orig_md5 = md5_file(path)
    print(f"[*] Original MD5: {orig_md5}")

    with open(path, "rb") as f:
        for i in range(n):
            pname = f"{path}.part{i+1}of{n}"
            with open(pname, "wb") as out:
                remaining = PART_SIZE
                while remaining > 0:
                    chunk = f.read(min(4 * 1024 * 1024, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)

            actual = os.path.getsize(pname)
            if actual == 0:
                os.remove(pname)
                continue

            part_md5 = md5_file(pname)
            print(f"[✓] Part {i+1}: {actual//(1024**2)} MB | MD5: {part_md5}")
            parts.append(pname)

    manifest_path = f"{path}.md5"
    with open(manifest_path, "w") as mf:
        mf.write(f"original={orig_md5}\n")
        for p in parts:
            mf.write(f"{os.path.basename(p)}={md5_file(p)}\n")
    print(f"[*] MD5 manifest saved: {manifest_path}")

    return parts


# ═══════════════════════════════════════════
#  TELEGRAM UPLOAD
# ═══════════════════════════════════════════
async def upload_large_file(client: TelegramClient, file_path: str) -> InputFileBig:
    file_size   = os.path.getsize(file_path)
    file_id     = random.randint(0, 2**63)
    total_parts = math.ceil(file_size / UPLOAD_CHUNK)

    print(f"    Total parts : {total_parts}")
    print(f"    Chunk size  : {UPLOAD_CHUNK // 1024} KB")

    with open(file_path, "rb") as f:
        for part_idx in range(total_parts):
            chunk = f.read(UPLOAD_CHUNK)
            if not chunk:
                break
            await client(SaveBigFilePartRequest(
                file_id=file_id,
                file_part=part_idx,
                file_total_parts=total_parts,
                bytes=chunk,
            ))
            done = (part_idx + 1) * UPLOAD_CHUNK
            pct  = min(done / file_size * 100, 100)
            print(
                f"\r    {pct:5.1f}%  {min(done, file_size)//(1024**2)}MB / {file_size//(1024**2)}MB",
                end="", flush=True
            )

    print()
    return InputFileBig(id=file_id, parts=total_parts, name=os.path.basename(file_path))


async def upload_to_telegram(parts: list, original_name: str):
    async with TelegramClient("session", api_id, api_hash) as client:
        await client.start(phone=phone)
        me = await client.get_me()
        print(f"[✓] Logged in as: {me.first_name}")

        total = len(parts)
        for i, p in enumerate(parts, 1):
            fname    = os.path.basename(p)
            size_mb  = os.path.getsize(p) // (1024 ** 2)
            part_md5 = md5_file(p)
            caption  = (
                f"📦 {original_name}\n"
                f"🗂 Part {i}/{total}\n"
                f"🔑 MD5: {part_md5}"
            )

            print(f"\n[↑] Uploading: {fname}  ({size_mb} MB)  [{i}/{total}]")
            print(f"    MD5: {part_md5}")

            input_file = await upload_large_file(client, p)

            await client(SendMediaRequest(
                peer="me",
                media=InputMediaUploadedDocument(
                    file=input_file,
                    mime_type="application/octet-stream",
                    attributes=[DocumentAttributeFilename(fname)],
                ),
                message=caption,
                random_id=random.randint(0, 2**63),
            ))
            print(f"[✓] Part {i}/{total} sent!")

    print("\n✅ All parts uploaded to Saved Messages!")


# ═══════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════
async def main():
    print("=" * 55)
    print("  GoFile / YouTube → Telegram Uploader")
    print("=" * 55)

    print("\nSource type select karanawa:")
    print("  1. GoFile  (https://gofile.io/d/XXXXX)")
    print("  2. YouTube (https://youtube.com/watch?v=XXXXX)")
    choice = input("Choice (1 or 2): ").strip()

    if choice == "2":
        # YouTube mode
        url = input("YouTube URL: ").strip()

        print("\nQuality select karanawa:")
        print("  1. Best (highest available)")
        print("  2. 4K  (2160p)")
        print("  3. 1080p")
        print("  4. 720p")
        print("  5. Audio only (MP3)")
        q_choice = input("Choice (1-5): ").strip()

        quality_map = {"1": "best", "2": "4k", "3": "1080p", "4": "720p", "5": "audio"}
        quality = quality_map.get(q_choice, "best")

        fname = download_youtube(url, quality)

    else:
        # GoFile mode
        url = input("\nGoFile link (https://gofile.io/d/XXXXX): ").strip()
        dl_url, fname, hdrs, server_md5 = get_gofile_direct_link(url)
        download_file(dl_url, fname, hdrs, expected_md5=server_md5)

    parts = split_file(fname)
    await upload_to_telegram(parts, fname)

    if input("\nLocal files delete? (y/n): ").strip().lower() == "y":
        targets = set(parts)
        if fname not in parts:
            targets.add(fname)
        manifest = f"{fname}.md5"
        if os.path.exists(manifest):
            targets.add(manifest)
        for f in targets:
            if os.path.exists(f):
                os.remove(f)
                print(f"[✓] Deleted: {f}")

    print("\n🎉 Done!")


if __name__ == "__main__":
    asyncio.run(main())
