"""Mock tool registry: generic, Unity-like and Unreal-like tools + noise generators."""
from __future__ import annotations
import math, random
from typing import Any, Callable

REGISTRY: dict[str, dict] = {}
IMPL: dict[str, Callable[..., Any]] = {}
CALL_LOG: list[tuple[str, dict]] = []


def tool(name: str, description: str, params: dict, required: list[str] | None = None):
    def deco(fn):
        REGISTRY[name] = {"type": "function", "function": {
            "name": name, "description": description,
            "parameters": {"type": "object", "properties": params,
                           "required": required if required is not None else list(params.keys())}}}
        IMPL[name] = fn
        return fn
    return deco


def schemas(names: list[str]) -> list[dict]:
    return [REGISTRY[n] for n in names]


def dispatch(name: str, args: dict) -> Any:
    CALL_LOG.append((name, args))
    fn = IMPL.get(name)
    if fn is None:
        if name.startswith(tuple(_VERBS)):
            return {"ok": True, "tool": name}
        return {"error": "unknown tool " + repr(name),
                "hint": "call only tools from the provided list"}
    try:
        return fn(**args)
    except TypeError as e:
        return {"error": "bad arguments: " + str(e)}


I = {"type": "integer"}
N = {"type": "number"}
B = {"type": "boolean"}


def _s(d: str, **kw) -> dict:
    return dict({"type": "string", "description": d}, **kw)


# ---------------------------------------------------------------- generic
@tool("get_weather", "Return current weather for a city.",
      {"city": _s("City name"),
       "unit": {"type": "string", "enum": ["celsius", "fahrenheit"],
                "description": "Temperature unit"}}, ["city"])
def get_weather(city: str, unit: str = "celsius"):
    base = {"Ankara": 21, "Istanbul": 24, "Izmir": 28, "Tokyo": 17}.get(city, 15)
    if unit not in ("celsius", "fahrenheit"):
        return {"error": "invalid unit " + repr(unit) + ", allowed: celsius, fahrenheit"}
    if unit == "fahrenheit":
        base = round(base * 9 / 5 + 32)
    return {"city": city, "temperature": base, "unit": unit, "condition": "clear"}


@tool("convert_currency", "Convert an amount between two currencies.",
      {"amount": dict(N, description="Amount to convert"),
       "from_currency": _s("ISO code, for example USD"),
       "to_currency": _s("ISO code, for example TRY")})
def convert_currency(amount: float, from_currency: str, to_currency: str):
    rates = {"USD": 1.0, "EUR": 0.92, "TRY": 41.5, "JPY": 156.0, "GBP": 0.79}
    a, b = rates.get(str(from_currency).upper()), rates.get(str(to_currency).upper())
    if a is None or b is None:
        return {"error": "unsupported currency"}
    return {"result": round(amount / a * b, 2), "rate": round(b / a, 4)}


@tool("calculate", "Evaluate an arithmetic expression. Supports + - * / ** and sqrt().",
      {"expression": _s("for example (3+4)*2")})
def calculate(expression: str):
    try:
        v = eval(expression, {"__builtins__": {}}, {"sqrt": math.sqrt, "pi": math.pi})
        return {"result": v}
    except Exception as e:
        return {"error": str(e)}


@tool("search_employees", "Search the employee directory.",
      {"department": _s("Department name, lowercase"),
       "min_years": dict(I, description="Minimum years of tenure"),
       "skill": _s("Required skill")}, ["department"])
def search_employees(department: str, min_years: int = 0, skill: str = ""):
    rows = [{"name": "Ayse", "dept": "engineering", "years": 6, "skills": ["python", "unity"]},
            {"name": "Baran", "dept": "engineering", "years": 2, "skills": ["cpp", "unreal"]},
            {"name": "Ceren", "dept": "design", "years": 9, "skills": ["ux"]},
            {"name": "Deniz", "dept": "engineering", "years": 11, "skills": ["cpp", "unity"]}]
    out = [r for r in rows if r["dept"] == str(department).lower() and r["years"] >= min_years
           and (not skill or str(skill).lower() in r["skills"])]
    return {"count": len(out), "results": out}


@tool("send_email", "Send an email. Only call after the user explicitly confirms.",
      {"to": _s("Recipient address"), "subject": _s("Subject"), "body": _s("Body text")})
def send_email(to: str, subject: str, body: str):
    return {"status": "sent", "to": to, "id": "msg_001"}


@tool("db_query", "Run a read-only SQL query against the analytics warehouse.",
      {"sql": _s("A SELECT statement"),
       "limit": dict(I, description="Max rows")}, ["sql"])
def db_query(sql: str, limit: int = 100):
    if not str(sql).strip().lower().startswith("select"):
        return {"error": "only SELECT is allowed"}
    return {"rows": [{"month": "2026-06", "revenue": 128400},
                     {"month": "2026-07", "revenue": 141900}], "truncated": False}


@tool("create_ticket", "Create an issue ticket in the tracker.",
      {"title": _s("Short title"),
       "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"],
                    "description": "Priority level"},
       "labels": {"type": "array", "items": {"type": "string"},
                  "description": "Label list"},
       "assignee": _s("Username or empty string")}, ["title", "priority"])
def create_ticket(title: str, priority: str, labels: list | None = None, assignee: str = ""):
    if priority not in ("low", "medium", "high", "critical"):
        return {"error": "invalid priority " + repr(priority)}
    return {"id": "ENG-4412", "title": title, "priority": priority,
            "labels": labels or [], "assignee": assignee}


@tool("schedule_meeting", "Schedule a calendar meeting.",
      {"title": _s("Meeting title"),
       "start_iso": _s("Start time, strict ISO-8601, for example 2026-08-21T14:00:00"),
       "duration_minutes": dict(I, description="Length in minutes"),
       "attendees": {"type": "array", "items": {"type": "string"},
                     "description": "Email addresses"},
       "recurrence": {"type": "object", "description": "Optional recurrence rule",
                      "properties": {"freq": {"type": "string",
                                              "enum": ["daily", "weekly", "monthly"]},
                                     "interval": {"type": "integer"},
                                     "count": {"type": "integer"}}}},
      ["title", "start_iso", "duration_minutes", "attendees"])
def schedule_meeting(title: str, start_iso: str, duration_minutes: int,
                     attendees: list, recurrence: dict | None = None):
    return {"event_id": "evt_77", "title": title, "start": start_iso,
            "duration": duration_minutes, "attendees": attendees,
            "recurrence": recurrence}


# ---------------------------------------------------------------- unity-like
@tool("unity_create_gameobject", "Create a GameObject in the open Unity scene.",
      {"name": _s("Object name"),
       "primitive": {"type": "string",
                     "enum": ["None", "Cube", "Sphere", "Capsule", "Cylinder", "Plane", "Quad"],
                     "description": "Primitive mesh to build from"},
       "position": {"type": "array", "items": {"type": "number"},
                    "description": "World position as [x,y,z]"},
       "parent_path": _s("Hierarchy path of parent, or empty for scene root")}, ["name"])
def unity_create_gameobject(name: str, primitive: str = "None",
                            position: list | None = None, parent_path: str = ""):
    if position is not None and (not isinstance(position, list) or len(position) != 3):
        return {"error": "position must be a 3-element array [x,y,z]"}
    path = (parent_path + "/" + name) if parent_path else ("/" + name)
    return {"ok": True, "instance_id": abs(hash(path)) % 100000, "path": path,
            "primitive": primitive, "position": position or [0, 0, 0]}


@tool("unity_add_component", "Add a component to an existing GameObject.",
      {"target_path": _s("Hierarchy path, for example /Player"),
       "component_type": _s("Component type name, for example Rigidbody"),
       "properties": {"type": "object", "description": "Initial property values"}},
      ["target_path", "component_type"])
def unity_add_component(target_path: str, component_type: str, properties: dict | None = None):
    known = {"Rigidbody", "BoxCollider", "SphereCollider", "MeshRenderer", "Light",
             "Camera", "AudioSource", "NavMeshAgent", "Animator"}
    if component_type not in known:
        return {"error": "unknown component " + repr(component_type),
                "known": sorted(known)}
    return {"ok": True, "target": target_path, "component": component_type,
            "properties": properties or {}}


@tool("unity_set_transform", "Set position, rotation or scale of a GameObject.",
      {"target_path": _s("Hierarchy path"),
       "position": {"type": "array", "items": {"type": "number"},
                    "description": "World position [x,y,z]"},
       "rotation_euler": {"type": "array", "items": {"type": "number"},
                          "description": "Euler angles [x,y,z] in degrees"},
       "scale": {"type": "array", "items": {"type": "number"},
                 "description": "Local scale [x,y,z]"}}, ["target_path"])
def unity_set_transform(target_path: str, position=None, rotation_euler=None, scale=None):
    return {"ok": True, "target": target_path, "position": position,
            "rotation": rotation_euler, "scale": scale}


@tool("unity_find_objects", "Find GameObjects in the open scene by name or component.",
      {"name_contains": _s("Substring to match, or empty for all"),
       "with_component": _s("Component type filter, or empty for all")}, [])
def unity_find_objects(name_contains: str = "", with_component: str = ""):
    scene = [{"path": "/Main Camera", "components": ["Camera"]},
             {"path": "/Directional Light", "components": ["Light"]},
             {"path": "/Ground", "components": ["MeshRenderer", "BoxCollider"]},
             {"path": "/Enemies/Enemy_01", "components": ["NavMeshAgent", "Animator"]},
             {"path": "/Enemies/Enemy_02", "components": ["NavMeshAgent"]}]
    out = [o for o in scene
           if (not name_contains or str(name_contains).lower() in o["path"].lower())
           and (not with_component or with_component in o["components"])]
    return {"count": len(out), "objects": out}


@tool("unity_manage_script", "Create, read, update or delete a C# script asset.",
      {"action": {"type": "string", "enum": ["create", "read", "update", "delete"],
                  "description": "Operation to perform"},
       "path": _s("Asset path, must start with Assets/ and end with .cs"),
       "contents": _s("Full file contents, required for create and update")},
      ["action", "path"])
def unity_manage_script(action: str, path: str, contents: str = ""):
    if not str(path).startswith("Assets/") or not str(path).endswith(".cs"):
        return {"error": "path must start with Assets/ and end with .cs"}
    if action in ("create", "update") and not contents:
        return {"error": "contents required for create and update"}
    if action == "read":
        return {"path": path, "contents": "// existing stub\npublic class Stub {}"}
    return {"ok": True, "action": action, "path": path, "bytes": len(contents)}


@tool("unity_run_tests", "Run Unity Test Runner tests.",
      {"mode": {"type": "string", "enum": ["EditMode", "PlayMode"],
                "description": "Test platform"},
       "filter": _s("Test name filter, or empty for all")}, ["mode"])
def unity_run_tests(mode: str, filter: str = ""):
    return {"mode": mode, "passed": 12, "failed": 1,
            "failures": ["EnemyPatrolTests.WaypointLoop_ReturnsToStart"]}


@tool("unity_console_read", "Read entries from the Unity editor console log.",
      {"levels": {"type": "array",
                  "items": {"type": "string", "enum": ["log", "warning", "error"]},
                  "description": "Levels to include"},
       "count": dict(I, description="Max entries to return")}, [])
def unity_console_read(levels=None, count: int = 20):
    return {"entries": [
        {"level": "error",
         "message": "NullReferenceException in EnemyAI.Update() at Assets/Scripts/EnemyAI.cs:42"},
        {"level": "warning", "message": "Shader Custom/Water has 2 unused properties"}]}


# ---------------------------------------------------------------- unreal-like
@tool("unreal_spawn_actor", "Spawn an actor into the current Unreal level.",
      {"actor_class": _s("Class path or name, for example StaticMeshActor"),
       "location": {"type": "array", "items": {"type": "number"},
                    "description": "[X,Y,Z] in centimetres"},
       "rotation": {"type": "array", "items": {"type": "number"},
                    "description": "[Pitch,Yaw,Roll] in degrees"},
       "label": _s("Actor label shown in the outliner")}, ["actor_class"])
def unreal_spawn_actor(actor_class: str, location=None, rotation=None, label: str = ""):
    return {"ok": True, "actor": label or actor_class, "class": actor_class,
            "location": location or [0, 0, 0], "rotation": rotation or [0, 0, 0]}


@tool("unreal_blueprint_add_node", "Add a node to a Blueprint event graph.",
      {"blueprint_path": _s("for example /Game/Blueprints/BP_Door"),
       "node_type": _s("Node type, for example K2Node_CallFunction"),
       "function_name": _s("Function to call, if applicable"),
       "position": {"type": "array", "items": {"type": "integer"},
                    "description": "[X,Y] graph coordinates"}},
      ["blueprint_path", "node_type"])
def unreal_blueprint_add_node(blueprint_path: str, node_type: str,
                              function_name: str = "", position=None):
    if not str(blueprint_path).startswith("/Game/"):
        return {"error": "blueprint_path must start with /Game/"}
    return {"ok": True, "node_id": "N_18", "blueprint": blueprint_path,
            "node_type": node_type, "function": function_name}


@tool("unreal_set_material", "Assign a material to a mesh actor material slot.",
      {"actor_label": _s("Actor label"),
       "slot_index": dict(I, description="Material slot index"),
       "material_path": _s("for example /Game/Materials/M_Metal")},
      ["actor_label", "slot_index", "material_path"])
def unreal_set_material(actor_label: str, slot_index: int, material_path: str):
    return {"ok": True, "actor": actor_label, "slot": slot_index, "material": material_path}


@tool("unreal_list_actors", "List actors present in the current level.",
      {"class_filter": _s("Class name filter, or empty for all")}, [])
def unreal_list_actors(class_filter: str = ""):
    actors = [{"label": "Floor", "class": "StaticMeshActor"},
              {"label": "PlayerStart", "class": "PlayerStart"},
              {"label": "Light_Sun", "class": "DirectionalLight"},
              {"label": "Door_A", "class": "BP_Door_C"}]
    if class_filter:
        actors = [a for a in actors if str(class_filter).lower() in a["class"].lower()]
    return {"count": len(actors), "actors": actors}


# ---------------------------------------------------------------- noise
_VERBS = ["fetch", "update", "sync", "validate", "render", "compress", "index", "purge",
          "rotate", "encode", "diff", "merge", "profile", "bake", "stream", "audit"]
_NOUNS = ["invoice", "shader", "lightmap", "manifest", "texture", "payroll", "sitemap",
          "changelog", "keystore", "telemetry", "playlist", "waypoint", "lodgroup",
          "colorspace", "navmesh", "atlas", "prefab", "cubemap", "spline", "decal"]


def noise_tools(n: int, seed: int = 7) -> list[dict]:
    """Plausible but irrelevant tools, used to bury the correct tool in a long list."""
    rnd = random.Random(seed)
    out: list[dict] = []
    seen: set[str] = set()
    while len(out) < n:
        name = rnd.choice(_VERBS) + "_" + rnd.choice(_NOUNS) + "_" + str(len(out)).zfill(3)
        if name in seen:
            continue
        seen.add(name)
        out.append({"type": "function", "function": {
            "name": name,
            "description": "Internal maintenance operation: " + name.replace("_", " ") +
                           ". Unrelated to weather, scenes, actors, tickets or currency.",
            "parameters": {"type": "object", "properties": {
                "target_id": {"type": "string", "description": "Opaque resource id"},
                "force": {"type": "boolean", "description": "Bypass safety checks"}},
                "required": ["target_id"]}}})
    return out
