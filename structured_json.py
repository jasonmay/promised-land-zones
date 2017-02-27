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

    out_data = {"loc": [], "obj": [], "mob": []}
    combined = {"loc": {}, "obj": {}, "mob": {}}
    for path in iter:
        d = json.loads(open(path, "r").read())
        for key in ["loc", "obj", "mob"]:
            combined[key] = dict(combined[key].items() + d[key].items())

    def add_prop(props, name, value):
        prop_datum = {'name': name, 'value': value}
        props.append(prop_datum)

    for loc_id, loc_data, in combined["loc"].iteritems():
        local_id, zone = loc_id.split('@')
        loc = {}

        props = []

        for data_key in ["title", "description"]:
            loc[data_key] = loc_data[data_key]

        add_prop(props, "altitude", loc_data["altitude"])

        if "flags" in loc_data:
            add_prop(props, 'flags', loc_data['flags'])

        loc['exits'] = []
        for direction in ["n", "s", "e", "w", "u", "d"]:
            if direction not in loc_data["exits"]:
                continue

            ex = loc_data["exits"][direction]
            exit_value = ensure_zone(ex.lstrip("^"), zone)

            exit_datum = {
                'direction': direction,
                'entity': exit_value,
            }
            if ex.startswith("^"):
                exit_datum['type'] = 'obj'
            else:
                exit_datum['type'] = 'loc'
            loc['exits'].append(exit_datum)

        loc["id"] = loc_id
        loc["properties"] = props

        out_data["loc"].append(loc)

    for obj_id, obj_data, in combined["obj"].iteritems():
        local_id, zone = obj_id.split('@')

        props = []

        if "oflag" in obj_data:
            obj_data['oflags'] = obj_data.pop('oflag', None)
        if "aflag" in obj_data:
            obj_data['aflags'] = obj_data.pop('aflag', None)

        if "location" in obj_data:
            if ":" not in obj_data["location"]:
                obj_data["location"] += ":" + zone

        for prop in ["visibility", "state", "examine[0]", "weight", "bvalue",
                    "desc[3]", "name", "desc[2]", "pname",
                    "examine[1]", "desc[0]", "damage", "examine", "size",
                    "desc[]", "maxstate", "desc[1]", "altname", "armor", "linked",
                    "location", "oflags", "aflags"]:
            if prop in obj_data:
                if prop == "linked":
                    p = ensure_zone(obj_data["linked"], zone)
                else:
                    p = obj_data[prop]

                add_prop(props, prop, p)

        out_data["obj"].append({
            'id': obj_id,
            'properties': props,
        })

    for mob_id, mob_data, in combined["mob"].iteritems():
        local_id, zone = mob_id.split('@')
        mob_key = ":".join([zone, local_id])

        props = []

        for flag_key in ["eflags", "sflag", "sflags",
                    "pflag", "pflags", "mflag", "mflags"]:
            if flag_key in mob_data:
                if flag_key.endswith("flag"):
                    flag_key_plural = flag_key + "s"
                    mob_data[flag_key_plural] = mob_data.pop(flag_key, None)
                    add_prop(props, flag_key_plural, mob_data[flag_key_plural])

        for prop in ["visibility", "damage", "examine", "strength", "desc", "speed",
                    "aggression", "location", "name", "armor", "description",
                    "wimpy", "pname"]:
            if prop in mob_data:
                if prop == "location":
                    dest = mob_data["location"]
                    mob_data[prop] = ensure_zone(dest, zone)
                add_prop(props, prop, mob_data[prop])

        out_data["mob"].append({
            'id': mob_id,
            'properties': props,
        })

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

    return ret
    #return ':'.join(reversed(ret.split("@"))).lower()


f = open(GEN_DIRECTORY + "/zones.json", "w")
f.write(json.dumps(generate_data(), indent=2))
f.close()
