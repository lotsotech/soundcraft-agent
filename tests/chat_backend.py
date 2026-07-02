"""
Headless chat backend for testing Jamie without Streamlit.
Runs a conversation and reports exactly what product IDs are stored per turn.

Usage:
    python -m tests.chat_backend                    # interactive REPL
    python -m tests.chat_backend --script "msg1|msg2|msg3"  # pipe messages
"""
import os, sys, argparse
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
from dotenv import load_dotenv
load_dotenv(os.path.join(_root, ".env"))

from agent.startup import ensure_db
ensure_db()

from agent.soundcraft_agent import SoundCraftAgent


def run_turn(agent: SoundCraftAgent, messages: list[dict], card_map: dict, user_input: str):
    messages.append({"role": "user", "content": user_input})
    reply, handoff = agent.send(user_input, messages)
    messages.append({"role": "assistant", "content": reply})

    ids = list(agent.last_recommended_ids)

    # Dedupe exactly as render_product_cards does
    seen = set()
    ids_deduped = [x for x in ids if not (x in seen or seen.add(x))]

    print(f"\nJamie: {reply[:300]}{'...' if len(reply) > 300 else ''}")
    print(f"  [last_recommended_ids ({len(ids)}): {ids}]")
    if len(ids) != len(ids_deduped):
        print(f"  *** DUPLICATES in last_recommended_ids: {ids} ***")
    if handoff:
        print(f"  [Handoff triggered: {handoff.get('handoff_id')}]")

    # Store in card_map exactly as app.py does
    if ids_deduped:
        idx = len(messages) - 1
        card_map[idx] = ids_deduped

    # Simulate full history loop render (what Streamlit does on every rerun)
    print(f"\n  card_map after turn: {card_map}")
    print(f"  Simulated history loop render:")
    total_cards = 0
    for i, msg in enumerate(messages):
        if i in card_map:
            print(f"    msg[{i}] ({msg['role']}): renders {len(card_map[i])} cards -> {card_map[i]}")
            total_cards += len(card_map[i])
    print(f"  Total cards rendered: {total_cards}")
    if total_cards != len(set(card_map.get(len(messages)-1, []))):
        # Only flag if cards from multiple turns are being shown (expected on multi-turn)
        turns_with_cards = [i for i in card_map]
        if len(turns_with_cards) > 1:
            print(f"  NOTE: cards from {len(turns_with_cards)} turns are visible in history")

    return reply, handoff


def interactive():
    agent = SoundCraftAgent()
    messages = []
    card_map = {}
    print("SoundCraft Chat Backend — type 'quit' to exit\n")
    print(f"Jamie: Hey there! Welcome to SoundCraft — I'm Jamie. What brings you in today?\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input or user_input.lower() == "quit":
            break
        run_turn(agent, messages, card_map, user_input)


def script_mode(script: str):
    agent = SoundCraftAgent()
    messages = []
    card_map = {}
    turns = [t.strip() for t in script.split("|") if t.strip()]
    print(f"Running {len(turns)} scripted turns...\n")
    for msg in turns:
        print(f"You: {msg}")
        run_turn(agent, messages, card_map, msg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", help="Pipe-separated messages to send e.g. 'hi|guitar around 500|beginner'")
    args = parser.parse_args()

    if args.script:
        script_mode(args.script)
    else:
        interactive()
