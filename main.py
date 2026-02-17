import os
import re
import math
import asyncio
import requests
from telethon import TelegramClient
from telethon.tl.functions.upload import SaveBigFilePartRequest, SaveFilePartRequest
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import (
    InputFileBig, InputFile,
    InputMediaUploadedDocument,
    DocumentAttributeFilename,
    MessageMediaDocument,
)
import hashlib
import random

# ====== YOUR API DETAILS ======
api_id = 38963550
api_hash = "1e7e73506dd3e91f2c513240e701945d"
phone = "+94704608828"
# ==============================

# Telegram hard limit = 2GB (2,000 MB exactly to be safe)
PART_SIZE = 1990 * 1024 * 1024   # 1990 MB — safe margin below 2GB
UPLOAD_CHUNK = 512 * 1024         # 512 KB upload chunks (must be multiple of 1024)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


# ─────────────────────────────────────────
# GoFile websiteToken — config.js eken
# ─────────────────────────────────────────
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
                print(f"[*] WebsiteToken (regex): {m.group(1)}")
                return m.group(1)

        raise Exception(f"Token pattern nemata. config.js:\n{js[:400]}")

    except Exception as e:
        raise Exception(
            f"config.js fail: {e}\n"
            "Manual: Browser F12 > Network > gofile API request > X-Website-Token header"
        )


# ─────────────────────────────────────────
# GoFile content resolve
# ─────────────────────────────────────────
def get_gofile_direct_link(page_url: str):
    if "/d/" not in page_url:
        raise ValueError("Valid GoFile link: https://gofile.io/d/XXXXX")

    content_id = page_url.rstrip("/").split("/d/")[-1]
    print(f"[*] Content ID : {content_id}")

    # Guest token
    r = requests.post(
        "https://api.gofile.io/accounts",
        headers={"User-Agent": UA}, timeout=15
    ).json()
    if r.get("status") != "ok":
        raise Exception(f"Guest token fail: {r}")
    guest_token = r["data"]["token"]
    print("[*] Guest token : OK")

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
            "error-notPremium": "X-Website-Token wrong/expired. Browser F12 eken manually check.",
            "error-notFound": "Content ID invalid.",
            "error-passwordRequired": "Password protected.",
        }
        raise Exception(f"GoFile error: {err}\n{tips.get(err, err)}")

    data = resp["data"]
    children = data.get("children", {})
    file_item = next((v for v in children.values() if v.get("type") == "file"), None)
    if not file_item:
        if data.get("type") == "file":
            file_item = data
        else:
            raise Exception("File nemata.")

    name = file_item["name"]
    url  = file_item["link"]
    size = file_item.get("size", 0)
    print(f"[*] File  : {name}")
    print(f"[*] Size  : {size // (1024**2)} MB")
    return url, name, headers


# ─────────────────────────────────────────
# Streaming downloader
# ─────────────────────────────────────────
def download_file(url: str, filename: str, headers: dict):
    print(f"\n[↓] Downloading: {filename}")
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=4 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        print(
                            f"\r    {done/total*100:5.1f}%  "
                            f"{done//(1024**2)}MB / {total//(1024**2)}MB",
                            end="", flush=True
                        )
    print(f"\n[✓] Download complete: {done//(1024**2)} MB")


# ─────────────────────────────────────────
# File splitter — FIXED
# ─────────────────────────────────────────
def split_file(path: str) -> list:
    """
    File eka PART_SIZE (1990MB) chunks walata split karanawa.
    Original file-ath part list ekata include — single part nattam.
    """
    size = os.path.getsize(path)
    n = math.ceil(size / PART_SIZE)
    print(f"\n[*] File size : {size/(1024**3):.3f} GB")
    print(f"[*] Parts     : {n} x ~{PART_SIZE//(1024**2)} MB")

    if n == 1:
        print("[*] Split karanna oni naha — file already 2GB walata yatata.")
        return [path]

    parts = []
    with open(path, "rb") as f:
        for i in range(n):
            pname = f"{path}.part{i+1}of{n}"
            written = 0
            with open(pname, "wb") as out:
                remaining = PART_SIZE
                while remaining > 0:
                    read_size = min(4 * 1024 * 1024, remaining)
                    chunk = f.read(read_size)
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)

            actual_size = os.path.getsize(pname)
            if actual_size == 0:
                # Empty part — remove it
                os.remove(pname)
                print(f"[!] Part {i+1} empty, skipping.")
                continue

            print(f"[✓] Part {i+1}: {actual_size//(1024**2)} MB  →  {pname}")
            parts.append(pname)

    return parts


# ─────────────────────────────────────────
# Large file upload — FIXED
# Telethon send_file 2GB handle karanna baha
# Manual SaveBigFilePartRequest use karanawa
# ─────────────────────────────────────────
async def upload_large_file(client: TelegramClient, file_path: str) -> InputFileBig:
    """
    2GB+ files Telegram ekata upload karanawa.
    SaveBigFilePartRequest manually use karanawa.
    Returns InputFileBig for use in SendMediaRequest.
    """
    file_size = os.path.getsize(file_path)
    file_id   = random.randint(0, 2**63)

    chunk_size    = UPLOAD_CHUNK                          # 512 KB
    total_parts   = math.ceil(file_size / chunk_size)

    print(f"    Total parts : {total_parts}")
    print(f"    Chunk size  : {chunk_size // 1024} KB")

    with open(file_path, "rb") as f:
        for part_idx in range(total_parts):
            chunk = f.read(chunk_size)
            if not chunk:
                break

            await client(SaveBigFilePartRequest(
                file_id=file_id,
                file_part=part_idx,
                file_total_parts=total_parts,
                bytes=chunk,
            ))

            done = (part_idx + 1) * chunk_size
            pct  = min(done / file_size * 100, 100)
            print(
                f"\r    {pct:5.1f}%  {min(done, file_size)//(1024**2)}MB / {file_size//(1024**2)}MB",
                end="", flush=True
            )

    print()
    return InputFileBig(
        id=file_id,
        parts=total_parts,
        name=os.path.basename(file_path),
    )


# ─────────────────────────────────────────
# Telegram uploader
# ─────────────────────────────────────────
async def upload_to_telegram(parts: list, original_name: str):
    async with TelegramClient("session", api_id, api_hash) as client:
        await client.start(phone=phone)
        me = await client.get_me()
        print(f"[✓] Logged in as: {me.first_name}")

        total = len(parts)
        for i, p in enumerate(parts, 1):
            fname    = os.path.basename(p)
            size_mb  = os.path.getsize(p) // (1024 ** 2)
            caption  = f"📦 {original_name}\n🗂 Part {i}/{total}"

            print(f"\n[↑] Uploading: {fname}  ({size_mb} MB)  [{i}/{total}]")

            # Manual large file upload
            input_file = await upload_large_file(client, p)

            # Send as document
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


# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────
async def main():
    print("=" * 55)
    print("  GoFile → Telegram Uploader")
    print("=" * 55)

    url = input("\nGoFile link (https://gofile.io/d/XXXXX): ").strip()

    dl_url, fname, hdrs = get_gofile_direct_link(url)
    download_file(dl_url, fname, hdrs)
    parts = split_file(fname)
    await upload_to_telegram(parts, fname)

    if input("\nLocal files delete? (y/n): ").strip().lower() == "y":
        targets = set(parts)
        if fname not in parts:
            targets.add(fname)
        for f in targets:
            if os.path.exists(f):
                os.remove(f)
                print(f"[✓] Deleted: {f}")

    print("\n🎉 Done!")


if __name__ == "__main__":
    asyncio.run(main())