# Work log

Track tasks, missions and daily logs, with a dashboard showing what's due by date and how you're doing.

## Run it (protected local server)

**One-time setup** (Python 3.10+ required; Windows: use `python` and `venv\Scripts\activate`):

    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    python manage.py makemigrations tracker
    python manage.py migrate
    python manage.py createsuperuser      # your first administrator

**Every time you want to use it:**

    python serve.py            # only this computer  -> http://127.0.0.1:8000
    python serve.py --lan      # also your home/office network -> the address it prints

Or just double-click `start.bat` (Windows) / run `./start.sh` (Mac, Linux). They set everything up on the first run and accept `--lan` too. Stop with Ctrl+C.

### Run it by itself (Windows)
- **Start automatically:** double-click `install_autostart.bat` once. From then on the server starts silently in the background (no window) each time you sign in to Windows, and shares on your network (`--lan`). Which networks it accepts is chosen with `network.bat` (see below). Undo with `uninstall_autostart.bat`.
- **Start it by hand without a window:** double-click `start_hidden.bat`.
- **Stop it safely:** sign in as a superuser and click **Shut down server** at the top right. It backs up the database, then stops. Start it again with `start_hidden.bat`.
- **Messages and errors** are written to `data/server.log` when it runs without a window.
- **Emergency stop** (if the website is unreachable): run `python backup.py`, then end `pythonw.exe` in Task Manager.
- **Automatic backups:** a backup is made when the server starts, every 12 hours, and when it stops, but only if something changed. The newest 40 are kept in `data/backups/` (change `BACKUP_EVERY_HOURS` and `BACKUP_KEEP` in `config/settings.py`).

### A friendly name instead of the IP address
With `--lan`, the server announces itself as **http://wondermanage.local** (change the name with the `WORKLOG_NAME` environment variable). The background start uses port 80, so no `:8000` is needed.
- One-time: run `venv\Scripts\pip install -r requirements.txt` (this adds `zeroconf`), then restart the server.
- Works on Windows 10/11, Mac, iPhone and iPad. Some Android phones don't understand `.local` names; use the IP address there, or give your router a DNS entry (below).
- Type the full `http://` the first time so the browser doesn't turn it into a search.
- On the server computer itself, use `http://localhost`.
- If port 80 is busy (another program uses it), the server logs an error in `data/server.log`; change `--port 80` in `worklog_hidden.vbs` back to `--port 8000`.
- Any device can also use the name if you add `192.168.110.200  wondermanage` to its hosts file, or add the same name in your router's local DNS / static DNS page if it has one (best option: works for every device). Give the laptop a fixed address in the router first.

### Appearance: name, logo and colours
Administrators (anyone with "Manage users and roles", and superusers) see **Appearance** in the top menu. There you can:
- change the **name** "Work log" to something personal (top of every page and the browser tab),
- upload a **logo** (PNG, JPG, GIF or WebP, under 1 MB; also used as the browser tab icon),
- pick a **colour palette** (Original, or a named palette, or "Your colour" with the colour picker). Page backgrounds follow the main colour, in light and dark mode.

Changes apply to everyone immediately. The settings and the logo are stored in the database (`data/db.sqlite3`), so they are included in every backup.

**One installation per business:** give each business its own copy of this folder (start from a clean copy, without someone else's `data/` folder). Each copy has its own database, users, name, logo and colours. The friendly network name (`wondermanage.local`) is separate: set `WORKLOG_NAME` to something else for each business if two run on the same network.

**Updating:** `serve.py` now creates and applies any database update by itself each time it starts, so you no longer need to run `makemigrations` / `migrate` by hand. If something goes wrong it writes the reason to `data/server.log`.

### Reach it from anywhere with Tailscale
When `network.bat` is set to option 3 (Tailscale), devices on your Tailscale network can open it even from mobile data or another Wi-Fi.
1. Tailscale must be installed and signed in on the server computer and on each phone or laptop that needs access, all in the same tailnet.
2. Find the server's Tailscale address: click the Tailscale icon in the Windows tray (or run `tailscale ip -4`). It looks like `100.x.x.x`.
3. On the other device, with Tailscale switched on, open `http://100.x.x.x`. If Tailscale's MagicDNS is on you can also use the computer's Tailscale name, e.g. `http://takwa` (include `http://`).
4. Traffic between the devices is already encrypted by Tailscale, even though the address starts with http.
5. If it does not connect, allow the port for Tailscale only (run once in a terminal opened as administrator):
   `netsh advfirewall firewall add rule name="WorkLog Tailscale" dir=in action=allow protocol=TCP localport=80 remoteip=100.64.0.0/10`
6. The server computer must be on, signed in to Windows, and not asleep. Set "Sleep" to Never while plugged in.
Everyone in your tailnet can reach the sign-in page, but still needs an account in the app. Tailscale access rules (ACLs) can narrow this further. To switch Tailscale access off, run `network.bat` and choose option 2.

### Switching between clients: network.bat
The server listens on every network card of the computer, so you never change an IP address inside the app. What differs per client is the address people type, and `network.bat` handles that:
- Double-click **network.bat**. It shows the current mode and the exact addresses to give people, then offers: **1** this computer only, **2** the client's local network, **3** Tailscale + local network.
- Your choice is saved in `data/network_mode.txt` and the server restarts by itself (a backup is made first). The choice survives reboots.
- Run **allow_firewall.bat** once as administrator on each computer. It opens port 80 for the local subnet and for Tailscale only. Without it, Windows on a new Wi-Fi marked "Public" blocks other devices.
- The local-network address comes from the client's router and can change. Use the `http://wondermanage.local` name, or ask the client to give this computer a fixed address ("DHCP reservation") in their router.
- Command line equivalents: `python serve.py --mode lan`, `--mode tailscale`, `--mode saved`, and `python serve.py --show`.

### Protecting the connection (stopping people on the Wi-Fi from spying or impersonating the server)
On the same Wi-Fi, someone can trick devices into sending their traffic through his laptop (ARP spoofing), or pretend to be `wondermanage.local` and show a fake login page. Plain http cannot stop that. Two options in `network.bat`:

**Option 4: Tailscale ONLY (strongest, nothing to install on devices except Tailscale).** The server refuses everything that is not this computer or a Tailscale device. Neighbours on the Wi-Fi cannot even log in, and Tailscale traffic is encrypted and authenticated. Use the Tailscale address (`http://100.x.x.x`) on every device.

**Option 5: Encrypted connection (HTTPS).** Everything, including passwords, travels encrypted, and devices can tell the real server from an impostor.
1. Choose option 5 (it turns on and restarts). Use `https://wondermanage.local` (or the https address shown in the menu). Typing plain `http://` is redirected, but bookmark the https address.
2. Choose option 6 and send the file `WorkLog-install-on-devices.crt` to each device by USB, AirDrop, e-mail or WhatsApp. Install it **once per device** (the server renews its own certificate whenever the network changes; nothing to redo):
   - **Windows:** double-click the file, Install Certificate, Local Machine, "Place all certificates in the following store", Trusted Root Certification Authorities. Firefox keeps its own list: Settings, Privacy & Security, View Certificates, Authorities, Import.
   - **Android:** Settings, Security, Encryption & credentials, Install a certificate, CA certificate, pick the file (Android then shows a "network may be monitored" notice; that is normal for a certificate you installed).
   - **iPhone / iPad:** open the file, allow the profile, install it in Settings, General, VPN & Device Management, then enable it in Settings, General, About, Certificate Trust Settings.
   - **Mac:** double-click the file, then in Keychain Access set it to "Always Trust".
   (Menus differ a little between versions.)
3. After this, a browser **warning** on that address means something is wrong. Do not click through it.

What HTTPS does not do: it cannot stop someone from jamming or blocking the connection, it does not help a device that is already infected, and the secret file `data/certs/ca.key` must never leave this computer (send only the `.crt`). The certificate authority is limited so that, even if the key were stolen, devices would only accept it for this server's name and private addresses, never for a real website. Browsers are told to insist on https for a week (HSTS); if you turn https off again, use the IP address until that week ends.

Also worth doing on the client's side: a strong WPA2/WPA3 Wi-Fi password (never an open network), a separate guest Wi-Fi, a changed router admin password, and BitLocker on this computer.

### Task numbers
Tasks no longer have a typed title. Each new task gets the next number automatically (T-0001, T-0002, ...). Numbers are never reused, even after a task is deleted. Tasks created earlier are numbered in the order they were created and keep their old title next to the number. Click a task to open its page, where the materials used are recorded.

### Inventory
**Inventory** (top menu) lists products and materials with the quantity in stock.
- **Add** a product or material: name, type, unit (pcs, kg, m, L...), optional reference and optional "warn me at or below" level.
- **Record a purchase** on its page: date, quantity and price per unit (plus supplier and note). Every purchase is kept, so you have the price history.
- **Stock** = everything bought minus everything used on tasks. It can go below zero if a purchase was not recorded yet; the item is then flagged.
- **Average cost** is the total spent divided by the total quantity bought.
- Items already used on a task can't be deleted (that would erase task history); untick **Active** to hide them instead.
- Set the **currency label** (e.g. TND) on the Appearance page.

### Materials used on a task
Open a task and use **Add material**: pick the product, enter the quantity. The cost per unit is filled in with the average price paid so far (people allowed to see prices can type another one). It is saved with the line, so later purchases at other prices don't change the cost of past tasks. Lines can be edited or removed at any time, and the task page shows the total material cost.

### Activity log
**Activity** (top menu) records who added, changed or deleted tasks, materials, inventory items and purchases, with the date, time and what changed. There is no way to edit or delete entries from the app.

### Who can do what
Everything above is switched on or off per role under **Users and roles**: inventory, purchases, materials on tasks, **See prices and costs**, and **See the activity log**. The Administrator role and superusers get everything. Other roles you created earlier start with none of the new permissions: open each role and tick what it should have. On a new installation, Member can use materials on tasks, Manager can also manage stock and see prices, and only Administrator sees the activity log.

### Where your data is stored
Everything private is in one folder, `data/`, inside the project:

- `data/db.sqlite3` is the database (all tasks, logs, locations, users and password hashes)
- `data/secret_key.txt` signs the login sessions; it is created automatically, so keep it private
- `data/backups/` holds the automatic backups, and any made by `python backup.py`

To back up by hand, copy the whole `data/` folder. To keep it elsewhere, set the `WORKLOG_DATA_DIR` environment variable. If you used an older version, a `db.sqlite3` next to `manage.py` is copied into `data/` automatically the first time.

### What protects it
- It listens on `127.0.0.1` unless you pass `--lan`, so nothing else can connect.
- Even in `--lan` mode, any visitor that is not on this computer or a private network address (192.168.x.x, 10.x.x.x, 172.16-31.x.x) gets a 403. Set `WORKLOG_LOCAL_ONLY=0` to switch this off (for example for a VPN that uses other addresses).
- Only host names it knows are accepted (`ALLOWED_HOSTS`).
- Everyone must sign in. After 5 wrong passwords from one address, sign-in is locked for 15 minutes. Passwords need 10+ characters, and sessions end after 12 hours.
- Debug mode is off, so errors never show internal details (`WORKLOG_DEBUG=1` turns it on while developing).
- The secret key is random and stored in `data/`, not in the code.
- On Mac/Linux the `data/` folder and database are readable only by your user account.

It speaks plain http, which is fine on your own network but means traffic is not encrypted. Do not open the port on your router or expose it to the internet. On a shared or untrusted Wi-Fi, use the default (this computer only).

## Users and roles
Everyone signs in. A **role** is a set of things a person is allowed to do, and each user has one role.
- Starter roles are created on the first `migrate`: Viewer (read only), Member (add and edit tasks, locations and logs), Manager (Member plus delete and manage mission types) and Administrator (everything, including user management).
- People with the "Manage users and roles" permission, and superusers, see a **Users and roles** link in the top menu. There they add users, set roles and passwords, deactivate accounts, and create or edit roles by ticking what each role can do. A table shows every role side by side.
- Tasks, locations and logs are shared by everyone. Roles decide who can see, add, edit and delete them.
- Safeguards: you can't deactivate or delete yourself, an administrator can't remove their own access, and only superusers can edit superusers.

## Locations
- On a task, the Location box searches your saved places as you type. If the place is new, choose "Add ... as a new location" and a popup lets you add it (with an optional map pin) without leaving the form.
- The Locations page lists every place next to a map of all pins. Click the map to add a location there.
- Map tiles, the Leaflet library and address search load from the internet (OpenStreetMap), so the map needs a connection.
- If the map shows "Access blocked" tiles, make sure you restarted the server after updating (the fix is in config/settings.py) and hard-refresh the page (Ctrl+Shift+R). You can also switch tile provider with MAP_TILE_URL in settings.py.
- Change where the map opens by default with MAP_DEFAULT_CENTER and MAP_DEFAULT_ZOOM in config/settings.py.

## Upgrading from an earlier version
Missions are now just a name. Keep your existing project folder, copy the new files over it, then run:

    python manage.py makemigrations tracker
    python manage.py migrate

After migrating, sign in with a superuser (create one with `createsuperuser` if you have none) and open Users and roles to add your team.

Old mission dates, locations and notes are dropped, and so is the free-text location on existing tasks (re-pick it from the new Location box). Tasks and logs are kept.

## Daily routine
1. Morning: open the dashboard, see today's row and anything overdue.
2. During the day: tick tasks as done (the circle), set each task's mission type, location and date.
3. Evening: "Write today's log". It pre-fills what you finished and what was due but wasn't done. Add hours worked.
