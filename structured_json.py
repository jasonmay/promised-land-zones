import glob
import json
import os

PL_NAMESPACE = os.environ["PL_NAMESPACE"]
GEN_DIRECTORY = os.environ["PL_GEN_DIRECTORY"]

# global neptune namespace
def g_namespace():
    return PL_NAMESPACE

def set_nested_value(o, k, p, v):
    if k not in o:
        o[k] = {}
    o[k][p] = v

def add_to_value(o, k, v):
    if k not in o:
        o[k] = []
    o[k].append(v)

def add_to_nested_value(o, k, p, v):
    if k not in o:
        o[k] = {}
    if p not in o[k]:
        o[k][p] = []
    o[k][p].append(v)

def generate_data():
    iter = glob.glob('./zones/*.json')

    movables_key = "%s:%s" % (g_namespace(), 'movables')
    hostiles_key = "%s:%s" % (g_namespace(), 'hostiles')

    mob_metadata = {}

    out_data = {}
    combined = {"loc": {}, "obj": {}, "mob": {}}
    for path in iter:
        d = json.loads(open(path, "r").read())
        for key in ["loc", "obj", "mob"]:
            combined[key] = dict(combined[key].items() + d[key].items())

    locations = combined["loc"]
    for loc_id, loc_data, in locations.iteritems():
        local_id, zone = loc_id.split('@')

        ns = lambda key: "%s:loc:%s:%s:%s" % (g_namespace(), zone, local_id, key)

        if ns("properties") not in out_data:
            out_data[ns("properties")] = {}

        for data_key in ["title", "description", "altitude"]:
            out_data[ns("properties")][data_key] = loc_data[data_key]

        if "flags" in loc_data:
            out_data[ns("flags")] = loc_data["flags"]

        for direction in ["n", "s", "e", "w", "u", "d"]:
            if direction not in loc_data["exits"]:
                continue

            ex = loc_data["exits"][direction]
            exit_value = ensure_zone(ex.lstrip("^"), zone)

            if ex.startswith("^"):
                object_link_key = "%s:%s:%s:%s:links" % (g_namespace(), "obj", zone, local_id)
                set_nested_value(out_data, object_link_key, direction, exit_value)
            else:
                if ns("exits") not in out_data:
                    out_data[ns("exits")] = {}
                out_data[ns("exits")][direction] = exit_value

    objects = combined["obj"]
    for obj_id, obj_data, in objects.iteritems():
        local_id, zone = obj_id.split('@')

        ns = lambda key: "%s:obj:%s:%s:%s" % (g_namespace(), zone, local_id, key)

        if ns("properties") not in out_data:
            out_data[ns("properties")] = {}
        for prop in ["visibility", "state", "examine[0]", "weight", "bvalue",
                    "desc[3]", "name", "desc[2]", "pname",
                    "examine[1]", "desc[0]", "damage", "examine", "size",
                    "desc[]", "maxstate", "desc[1]", "altname", "armor", "linked"]:
            if prop in obj_data:
                if prop == "linked":
                    out_data[ns("properties")][prop] = ensure_zone(obj_data["linked"], zone)
                else:
                    out_data[ns("properties")][prop] = obj_data[prop]

        if "oflag" in obj_data:
            out_data[ns("oflags")] = obj_data["oflag"]
        for flags in ["oflags", "aflags"]:
            if flags in obj_data:
                out_data[ns(flags)] = obj_data[flags]

        if "location" in obj_data:
            if ":" not in obj_data["location"]:
                obj_data["location"] += ":" + zone

            loc_type, dest = obj_data["location"].split(":")
            dest_value = ensure_zone(dest, zone)

            val = ':'.join([zone, local_id])
            add_to_redis_sets(ns, out_data, loc_type, dest_value, val)

    mobiles = combined["mob"]
    for mob_id, mob_data, in mobiles.iteritems():
        local_id, zone = mob_id.split('@')
        mob_key = ":".join([zone, local_id])

        ns = lambda key: "%s:mob:%s:%s:%s" % (g_namespace(), zone, local_id, key)

        if ns("properties") not in out_data:
            out_data[ns("properties")] = {}
        for prop in ["visibility", "damage", "examine", "strength", "desc", "speed",
                    "aggression", "location", "name", "armor", "description",
                    "wimpy", "pname"]:
            if prop in mob_data:
                out_data[ns("properties")][prop] = mob_data[prop]
                if prop == "location":
                    dest = mob_data["location"]
                    dest_value = ensure_zone(dest, zone)

                    room_key = ":".join([g_namespace(), "loc", dest_value, "mobs"])
                    add_to_value(out_data, room_key, mob_key)
                    out_data[ns("properties")]["location"] = dest_value

        # when are mobiles ...immobile:
        #   In a room with NO exits (TODO)
        #   In a room where every exit is any of the following:
        #     1) a closed door (TODO)
        #     2) a room with the NoMobiles flag (TODO)
        #   Has no speed or speed is 0
        if "speed" in mob_data:
            if int(mob_data["speed"]) > 0:
                set_nested_value(mob_metadata, mob_key, "movable", 1)

        if "aggression" in mob_data:
            if int(mob_data["aggression"]) > 0:
                set_nested_value(mob_metadata, mob_key, "hostile", 1)

        for flags in ["eflags", "sflag", "sflags",
                    "pflag", "pflags", "mflag", "mflags"]:
            if prop in mob_data:
                flag_key = prop
                if flag_key.endswith("g"):
                    flag_key += "s"
                out_data[ns("properties")][flag_key] = mob_data[prop]

    # movables set
    out_data[movables_key] = [ mk for mk, mv, in mob_metadata.iteritems()
                               if "movable" in mv ]


    # hostiles set
    out_data[hostiles_key] = [ mk for mk, mv, in mob_metadata.iteritems()
                               if "hostile" in mv ]
    return out_data

def add_to_redis_sets(ns, out_data, loc_type, dest_value, val):
    if loc_type == "IN_ROOM":
        room_key = ":".join([g_namespace(), "loc", dest_value, "objs"])
        add_to_value(out_data, room_key, val)
        out_data[ns("location")] = dest_value
    elif loc_type == "IN_CONTAINER":
        cont_key = ":".join([g_namespace(), "obj", dest_value, "containing"])
        add_to_value(out_data, cont_key, val)
        out_data[ns("container")] = dest_value
    elif loc_type == "WIELDED_BY":
        wield_key = ":".join([g_namespace(), "mob", dest_value, "wielding"])
        out_data[wield_key] = val # only one at a time
        out_data[ns("wieldedby")] = dest_value
    elif loc_type == "WORN_BY":
        wear_key = ":".join([g_namespace(), "mob", dest_value, "wearing"])
        add_to_value(out_data, wear_key, val)
        out_data[ns("wornby")] = dest_value
    elif loc_type == "CARRIED_BY":
        carry_key = ":".join([g_namespace(), "mob", dest_value, "carrying"])
        add_to_value(out_data, carry_key, val)
        out_data[ns("carriedby")] = dest_value

def ensure_zone(val, zone):
    ret = val
    if "@" not in ret:
        ret += "@" + zone

    return ':'.join(reversed(ret.split("@"))).lower()


f = open(GEN_DIRECTORY + "/zones.json", "w")
f.write(json.dumps(generate_data(), indent=2))
f.close()
