"""Poste un fichier texte/markdown sur un webhook Discord, découpé en messages de moins de 2000 caractères.

Usage : python post_discord.py <webhook_url> <fichier.md>
"""

import json
import sys
import time
import urllib.request


def chunks(text, size=1900):
    out, cur = [], ""
    for block in text.strip().split("\n\n"):
        while len(block) > size:  # bloc trop long : on coupe à la ligne
            cut = block.rfind("\n", 0, size)
            cut = cut if cut > 0 else size
            if cur:
                out.append(cur)
                cur = ""
            out.append(block[:cut])
            block = block[cut:].lstrip("\n")
        if cur and len(cur) + len(block) + 2 > size:
            out.append(cur)
            cur = ""
        cur += ("\n\n" if cur else "") + block
    if cur:
        out.append(cur)
    return out


def main():
    url, path = sys.argv[1], sys.argv[2]
    text = open(path, encoding="utf-8").read()
    for part in chunks(text):
        req = urllib.request.Request(url, data=json.dumps({"content": part}).encode(), headers={
            "Content-Type": "application/json", "User-Agent": "eco-calendar-bot/2.0"})
        urllib.request.urlopen(req, timeout=30).read()
        time.sleep(1)
    print("Publié sur Discord.")


if __name__ == "__main__":
    main()
