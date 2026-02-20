import os
import re
import math
import asyncio
import requests
from telethon import TelegramClient
from telethon.tl.functions.upload import SaveBigFilePartRequest
from telethon.tl.functions.messages import SendMediaRequest
from telethon.tl.types import (
    InputFileBig,
    InputMediaUploadedDocument,
    DocumentAttributeFilename,
)
import random

# ====== YOUR API DETAILS ======
api_id   = 38963550
api_hash = "1e7e73506dd3e91f2c513240e701945d"
phone    = "+94704608828"
# ==============================

PART_SIZE   = 1990 * 1024 * 1024   # 1990 MB
UPLOAD_CHUNK = 512 * 1024           # 512 KB
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


# ═══════════════════════════════════════════
#  SOURCE DETECTION
# ═══════════════════════════════════════════
def detect_source(url: str) -> str:
    """URL eka balala source eka detect karanawa."""
    if "gofile.io" in url:
        return "gofile"
    if "drive.google.com" in url or "docs.google.com" in url:
        return "gdrive"
    raise ValueError("Supported sources: GoFile (gofile.io) | Google Drive (drive.google.com)")


# ═══════════════════════════════════════════
#  GOOGLE DRIVE SUPPORT
# ═══════════════════════════════════════════
def extract_gdrive_file_id(url: str) -> str:
    """Google Drive URL ekata file ID extract karanawa."""
    # Format: /file/d/FILE_ID/view  or  ?id=FILE_ID
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]{10,})",
        r"id=([a-zA-Z0-9_-]{10,})",
        r"/d/([a-zA-Z0-9_-]{10,})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    raise ValueError(f"Google Drive file ID extract karannat bari: {url}")


def get_gdrive_direct_link(page_url: str):
    """
    Google Drive direct download link + filename + size return karanawa.
    gdown library use karanawa (pip install gdown).
    """
    try:
        import gdown
    except ImportError:
        raise ImportError(
            "gdown install karanna: pip install gdown"
        )

    file_id = extract_gdrive_file_id(page_url)
    print(f"[*] Google Drive File ID: {file_id}")

    # Metadata fetch
    meta_url = f"https://drive.google.com/uc?id={file_id}&export=download"

    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    resp = session.get(meta_url, allow_redirects=False, timeout=15)

    # Filename extract from headers
    fname = None
    if "Content-Disposition" in resp.headers:
        cd = resp.headers["Content-Disposition"]
        m = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';\n]+)', cd)
        if m:
            fname = m.group(1).strip()

    # Large file — virus scan warning bypass
    if resp.status_code == 302 or "accounts.google.com" not in resp.headers.get("location", ""):
        # Use gdown to get real URL (handles confirm token)
        direct_url = f"https://drive.google.com/uc?id={file_id}&export=download&confirm=t"
    else:
        direct_url = meta_url

    # Try to get size
    head = session.head(direct_url, allow_redirects=True, timeout=15)
    size = int(head.headers.get("content-length", 0))

    if not fname:
        # Try from URL or default
        cd = head.headers.get("Content-Disposition", "")
        m = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';\n]+)', cd)
        fname = m.group(1).strip() if m else f"gdrive_{file_id}"

    # URL decode filename
    from urllib.parse import unquote
    fname = unquote(fname)

    print(f"[*] File  : {fname}")
    print(f"[*] Size  : {size // (1024**2)} MB" if size else "[*] Size  : Unknown")

    return direct_url, fname, file_id, session


def download_gdrive_file(file_id: str, filename: str):
    """gdown use karala Google Drive file download karanawa."""
    try:
        import gdown
    except ImportError:
        raise ImportError("pip install gdown")

    print(f"\n[↓] Google Drive ekata download karanawa: {filename}")
    url = f"https://drive.google.com/uc?id={file_id}"
    gdown.download(url, filename, quiet=False, fuzzy=True)

    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        raise Exception("Download fail — file empty or missing.")

    size = os.path.getsize(filename)
    print(f"[✓] Download complete: {size // (1024**2)} MB")


# ═══════════════════════════════════════════
#  GOFILE SUPPORT  (original code — unchanged)
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
                print(f"[*] WebsiteToken (regex): {m.group(1)}")
                return m.group(1)

        raise Exception(f"Token pattern nemata. config.js:\n{js[:400]}")
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
            "error-notPremium": "X-Website-Token wrong/expired.",
            "error-notFound"  : "Content ID invalid.",
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


def download_gofile(url: str, filename: str, headers: dict):
    print(f"\n[↓] GoFile ekata download karanawa: {filename}")
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done  = 0
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


# ═══════════════════════════════════════════
#  FILE SPLITTER
# ═══════════════════════════════════════════
def split_file(path: str) -> list:
    size = os.path.getsize(path)
    n    = math.ceil(size / PART_SIZE)
    print(f"\n[*] File size : {size/(1024**3):.3f} GB")
    print(f"[*] Parts     : {n} x ~{PART_SIZE//(1024**2)} MB")

    if n == 1:
        print("[*] Split karanna oni naha — file already 2GB walata yatata.")
        return [path]

    parts = []
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

            print(f"[✓] Part {i+1}: {actual//(1024**2)} MB → {pname}")
            parts.append(pname)

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
            fname   = os.path.basename(p)
            size_mb = os.path.getsize(p) // (1024 ** 2)
            caption = f"📦 {original_name}\n🗂 Part {i}/{total}"

            print(f"\n[↑] Uploading: {fname}  ({size_mb} MB)  [{i}/{total}]")
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
    print("  GoFile / Google Drive → Telegram Uploader")
    print("=" * 55)
    print("\nSupported links:")
    print("  • GoFile      : https://gofile.io/d/XXXXX")
    print("  • Google Drive: https://drive.google.com/file/d/XXXXX/view")

    url    = input("\nLink paste karanna: ").strip()
    source = detect_source(url)

    fname = None
    try:
        if source == "gofile":
            print("\n[*] Source: GoFile")
            dl_url, fname, hdrs = get_gofile_direct_link(url)
            download_gofile(dl_url, fname, hdrs)

        elif source == "gdrive":
            print("\n[*] Source: Google Drive")
            _dl_url, fname, file_id, _session = get_gdrive_direct_link(url)
            download_gdrive_file(file_id, fname)

        parts = split_file(fname)
        await upload_to_telegram(parts, fname)

        if input("\nLocal files delete karanna? (y/n): ").strip().lower() == "y":
            targets = set(parts)
            if fname and fname not in parts:
                targets.add(fname)
            for f in targets:
                if os.path.exists(f):
                    os.remove(f)
                    print(f"[✓] Deleted: {f}")

    except Exception as e:
        print(f"\n[✗] Error: {e}")
        raise

    print("\n🎉 Done!")


if __name__ == "__main__":
    asyncio.run(main())