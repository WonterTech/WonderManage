"""What a role can be allowed to do, in plain words, plus the roles created on first setup."""

AREAS = [
    {"title": "Tasks", "view": "view_task", "perms": [
        ("view_task", "See tasks", "Open the task list, the calendar and the statistics."),
        ("add_task", "Add tasks", ""),
        ("change_task", "Edit tasks", "Change details and tick tasks done or not done."),
        ("delete_task", "Delete tasks", ""),
    ]},
    {"title": "Mission types", "view": "view_mission", "perms": [
        ("view_mission", "See mission types", ""),
        ("add_mission", "Add mission types", ""),
        ("change_mission", "Rename mission types", ""),
        ("delete_mission", "Delete mission types", ""),
    ]},
    {"title": "Locations", "view": "view_location", "perms": [
        ("view_location", "See locations and the map", ""),
        ("add_location", "Add locations", "Includes adding one while filling in a task."),
        ("change_location", "Edit locations and pins", ""),
        ("delete_location", "Delete locations", ""),
    ]},
    {"title": "Daily log", "view": "view_dailylog", "perms": [
        ("view_dailylog", "See daily logs", ""),
        ("add_dailylog", "Write today's log", ""),
        ("change_dailylog", "Edit logs", ""),
        ("delete_dailylog", "Delete logs", ""),
    ]},
    {"title": "Inventory", "view": "view_inventoryitem", "perms": [
        ("view_inventoryitem", "See the inventory", "Open the list of products and materials, with stock levels."),
        ("add_inventoryitem", "Add products and materials", ""),
        ("change_inventoryitem", "Edit products and materials", ""),
        ("delete_inventoryitem", "Delete products and materials", "Only possible while no task has used them."),
        ("add_purchase", "Record purchases", "Add stock together with the price paid."),
        ("change_purchase", "Edit purchases", ""),
        ("delete_purchase", "Delete purchases", ""),
    ]},
    {"title": "Materials used on tasks", "view": "view_taskmaterial", "perms": [
        ("view_taskmaterial", "See materials used on tasks", ""),
        ("add_taskmaterial", "Add materials to a task", ""),
        ("change_taskmaterial", "Edit materials used", ""),
        ("delete_taskmaterial", "Remove materials from a task", ""),
    ]},
    {"title": "Facturation", "view": "view_document", "perms": [
        ("view_document", "See factures and bons de livraison", "Open the Facturation tab, with client details and amounts."),
        ("add_document", "Create factures and bons de livraison", "Includes turning a bon de livraison into a facture."),
        ("change_document", "Edit them and change their status", "Also edits your company details shown on the documents."),
        ("delete_document", "Delete drafts", "Only drafts and cancelled documents can be deleted."),
    ]},
    {"title": "Prices and costs", "view": None, "perms": [
        ("view_costs", "See prices and costs", "Purchase prices, average cost, and the cost of materials on each task. Without this, people see quantities only."),
    ]},
    {"title": "Activity log", "view": "view_activitylog", "perms": [
        ("view_activitylog", "See the activity log", "Who added, changed or deleted tasks, materials, stock and purchases, and when. Give it only to people you trust."),
    ]},
    {"title": "Administration", "view": None, "perms": [
        ("manage_users", "Manage users and roles", "Create users, give them a role, and change what each role can do."),
    ]},
]

ALL_CODENAMES = [code for area in AREAS for code, _label, _help in area["perms"]]

_VIEW = ["view_task", "view_mission", "view_location", "view_dailylog", "view_inventoryitem", "view_taskmaterial"]
_MEMBER = _VIEW + [
    "add_task", "change_task", "add_location", "change_location", "add_dailylog", "change_dailylog",
    "add_taskmaterial", "change_taskmaterial", "delete_taskmaterial",
]
_MANAGER = _MEMBER + [
    "delete_task", "add_mission", "change_mission", "delete_mission", "delete_location", "delete_dailylog",
    "add_inventoryitem", "change_inventoryitem", "delete_inventoryitem",
    "add_purchase", "change_purchase", "delete_purchase", "view_costs",
    "view_document", "add_document", "change_document", "delete_document",
]

DEFAULT_ROLES = [
    ("Viewer", _VIEW),
    ("Member", _MEMBER),
    ("Manager", _MANAGER),
    ("Administrator", ALL_CODENAMES),
]


def seed_default_roles():
    """Create the starter roles, but only if no roles exist yet."""
    from django.contrib.auth.models import Group, Permission

    if Group.objects.exists():
        return
    perms = {
        p.codename: p
        for p in Permission.objects.filter(content_type__app_label="tracker", codename__in=ALL_CODENAMES)
    }
    for name, codenames in DEFAULT_ROLES:
        group = Group.objects.create(name=name)
        group.permissions.set([perms[c] for c in codenames if c in perms])


def sync_administrator_role():
    """The Administrator role always gets every permission, including ones added by an update."""
    from django.contrib.auth.models import Group, Permission

    group = Group.objects.filter(name="Administrator").first()
    if not group:
        return
    have = set(group.permissions.values_list("pk", flat=True))
    wanted = Permission.objects.filter(content_type__app_label="tracker", codename__in=ALL_CODENAMES)
    missing = [p for p in wanted if p.pk not in have]
    if missing:
        group.permissions.add(*missing)
