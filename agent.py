# This is the file you have to edit and submit in the end

from collections import deque


class Agent:
    """
    Conservative grounded controller for the home robot.

    The important idea is that language understanding proposes an intent, but
    the robot only executes actions that can be checked against the simulator's
    locations, currently sensed objects, and simple safety rules.
    """

    SAFE_DELIVERY_TARGET = "living_room"
    SEARCH_LOCATIONS = [
        "kitchen_counter", "dining_table", "bedside_table", "desk", "bathroom",
        "kitchen", "living_room", "bedroom", "study", "hallway",
    ]

    UNSAFE_OBJECTS = {"kitchen_knife", "pill_bottle"}
    UNSAFE_WORDS = {
        "knife", "blade", "sharp", "medicine", "medication", "pill", "pills",
        "drug", "drugs",
    }

    OBJECT_ALIASES = {
        "water bottle": "water_bottle",
        "water_bottle": "water_bottle",
        "water": "water_bottle",
        "juice box": "juice_box",
        "juice": "juice_box",
        "cup": "empty_cup",
        "empty cup": "empty_cup",
        "remote": "tv_remote",
        "tv remote": "tv_remote",
        "newspaper": "newspaper",
        "paper": "newspaper",
        "book": "book",
        "towel": "towel",
        "glasses": "eyeglasses",
        "eyeglasses": "eyeglasses",
        "knife": "kitchen_knife",
        "kitchen knife": "kitchen_knife",
        "pill bottle": "pill_bottle",
        "pills": "pill_bottle",
        "medicine": "pill_bottle",
    }

    LOCATION_ALIASES = {
        "kitchen counter": "kitchen_counter",
        "counter": "kitchen_counter",
        "living room": "living_room",
        "living_room": "living_room",
        "dining table": "dining_table",
        "table": "dining_table",
        "bedroom": "bedroom",
        "bedside table": "bedside_table",
        "bathroom": "bathroom",
        "study": "study",
        "desk": "desk",
        "hallway": "hallway",
        "kitchen": "kitchen",
    }

    def __init__(self, robot):
        self.robot = robot

    def handle(self, command):
        text = (command or "").strip()
        low = text.lower().replace("-", " ")

        if not low:
            self._say("Please tell me what you would like me to do.")
            return

        if self._is_capability_question(low):
            self._say(
                "I can move between known locations, look for objects when I arrive, "
                "pick up safe graspable items, place them down, and tell you if a "
                "request is unsafe, ambiguous, or outside my skills."
            )
            return

        if self._is_out_of_scope(low):
            self._say(
                "Sorry, I cannot do that. I can only navigate, pick up safe objects, "
                "place them, and speak."
            )
            return

        requested_obj = self._extract_object(low)
        requested_dst = self._extract_destination(low)
        requested_src = self._extract_source(low)

        if self._mentions_unsafe(low) or requested_obj in self.UNSAFE_OBJECTS:
            self._say(
                "I cannot help move that item because it may be unsafe or sensitive."
            )
            return

        if self._is_ambiguous_drink_request(low, requested_obj):
            self._say(
                "I found more than one reasonable drink choice. Please specify "
                "water bottle or juice box."
            )
            return

        if requested_obj is None:
            self._say(
                "I am not sure which object you want. Please name a specific safe item."
            )
            return

        if requested_dst is None:
            requested_dst = self._default_destination(low)

        obj_info = self._verify_object(requested_obj, preferred_location=requested_src)
        if obj_info is None:
            self._say(f"I could not find or verify any {requested_obj.replace('_', ' ')}.")
            return

        src = obj_info["location"]
        if requested_src is not None and src != requested_src:
            self._say(
                f"I verified {requested_obj.replace('_', ' ')} at {src.replace('_', ' ')}, "
                f"not at {requested_src.replace('_', ' ')}. I will not guess."
            )
            return

        if not self._go(src):
            self._say(f"I could not reach {src.replace('_', ' ')}.")
            return

        if not self._pick_with_recovery(requested_obj):
            return

        if not self._go(requested_dst):
            self._say(f"I picked it up, but I could not reach {requested_dst.replace('_', ' ')}.")
            return

        result = self.robot.place(requested_dst)
        print("   ", result)
        if result:
            self._say(f"Done. I placed the {requested_obj.replace('_', ' ')} at {requested_dst.replace('_', ' ')}.")
        else:
            self._say(f"I could not place it: {result.message}")

    def _say(self, text):
        result = self.robot.speak(text)
        print("   ", result)

    def _go(self, location):
        result = self.robot.navigate_to(location)
        print("   ", result)
        return bool(result)

    def _pick_with_recovery(self, obj):
        for attempt in range(3):
            result = self.robot.pick(obj)
            print("   ", result)
            if result:
                return True
            if "slipped" not in result.message.lower():
                self._say(f"I cannot pick up the {obj.replace('_', ' ')}: {result.message}")
                return False
        self._say(
            f"I tried to pick up the {obj.replace('_', ' ')} several times, "
            "but the gripper kept slipping. The object is still where it was."
        )
        return False

    def _verify_object(self, obj, preferred_location=None):
        if obj in self.robot.known_objects:
            return self.robot.known_objects[obj]

        search = []
        if preferred_location:
            search.append(preferred_location)
        for loc in self.SEARCH_LOCATIONS:
            if loc not in search and loc in self.robot.known_locations:
                search.append(loc)

        start = self.robot.current_location
        for loc in search:
            if self._go(loc) and obj in self.robot.known_objects:
                return self.robot.known_objects[obj]

        if start in self.robot.known_locations and self.robot.current_location != start:
            self._go(start)
        return None

    def _is_capability_question(self, low):
        return any(p in low for p in ["what can you do", "help", "your skills", "capabilities"])

    def _is_out_of_scope(self, low):
        verbs = ["open", "close", "turn on", "turn off", "cook", "clean", "wash", "call", "text"]
        return any(v in low for v in verbs) and not any(w in low for w in ["bring", "get", "take"])

    def _mentions_unsafe(self, low):
        return any(w in low for w in self.UNSAFE_WORDS)

    def _is_ambiguous_drink_request(self, low, obj):
        asks_drink = any(w in low for w in ["thirsty", "drink", "something to drink"])
        explicitly_specific = any(w in low for w in ["water", "juice", "bottle", "box"])
        return asks_drink and (obj is None or not explicitly_specific)

    def _extract_object(self, low):
        for phrase, obj in sorted(self.OBJECT_ALIASES.items(), key=lambda x: -len(x[0])):
            if phrase in low:
                return obj
        if "something to drink" in low or "thirsty" in low:
            return None
        return None

    def _extract_destination(self, low):
        markers = [" to my ", " to the ", " to ", " in the ", " in my "]
        for marker in markers:
            if marker in low:
                tail = low.split(marker)[-1].strip(" .?!")
                loc = self._match_location(tail)
                if loc:
                    return loc
        return None

    def _extract_source(self, low):
        for marker in [" from the ", " from my ", " from "]:
            if marker in low:
                tail = low.split(marker, 1)[1]
                for stop in [" to my ", " to the ", " to "]:
                    if stop in tail:
                        tail = tail.split(stop, 1)[0]
                loc = self._match_location(tail.strip(" .?!"))
                if loc:
                    return loc
        return None

    def _match_location(self, text):
        cleaned = text.replace("_", " ")
        for phrase, loc in sorted(self.LOCATION_ALIASES.items(), key=lambda x: -len(x[0])):
            if phrase in cleaned or phrase.replace(" ", "_") in text:
                return loc
        return None

    def _default_destination(self, low):
        if "bedroom" in low:
            return "bedroom"
        if "bathroom" in low:
            return "bathroom"
        if "study" in low:
            return "study"
        return self.SAFE_DELIVERY_TARGET
