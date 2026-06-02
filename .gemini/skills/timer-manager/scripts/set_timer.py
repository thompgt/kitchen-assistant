import argparse
import sys
import time
import threading

def set_timer(duration, label):
    print(f"Timer started: {label} for {duration} seconds.")
    # In a real app, this would probably be a background task or push to a queue.
    # For this simulation, we'll just exit after printing.
    sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set a kitchen timer.")
    parser.add_argument("--duration", type=int, required=True, help="Duration in seconds")
    parser.add_argument("--label", type=str, required=True, help="Label for the timer")
    
    args = parser.parse_args()
    set_timer(args.duration, args.label)
