#!/usr/bin/env python3

# python3 -m scripts.instant_follow_up
from service import *

def main():
    user_id = "orange_1"

    # Initialize services
    mem0_service = Mem0Service()
    mem0_service.add_memory(user_id, "I love Italian food, especially red sauce asta")


if __name__ == "__main__":
    main()
