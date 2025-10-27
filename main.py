import tkinter as tk
from tkinter import ttk, messagebox
import requests
import math
import webbrowser
import threading

IPINFO_URL = "https://ipinfo.io/json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "NearestWashroomFinder/1.0 (grady.korchinski@gmail.
com)"

HEADERS = {"User-Agent": USER_AGENT}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2.0)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


def format_distance(meters):
    if meters >= 1000:
        return f"{meters/1000:.2f} km"
    else:
        return f"{int(meters)} m"

def detect_location_by_ip():
    try:
        resp = requests.get(IPINFO_URL, headers=HEADERS, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if "loc" in data:
            lat_str, lon_str = data["loc"].split(",")
            return float(lat_str), float(lon_str), data.get("city"), data.get("region"), data.get("country")
        else:
            return None
    except Exception as e:
        return None


def geocode_address(address):
    try:
        params = {
            "q": address,
            "format": "json",
            "limit": 3,
        }
        resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        r = results[0]
        return float(r["lat"]), float(r["lon"]), r.get("display_name")
    except Exception as e:
        return None


def query_overpass(lat, lon, radius_m):
    query = f"""
[out:json][timeout:25];
(
  node["amenity"="toilets"](around:{int(radius_m)},{lat},{lon});
  way["amenity"="toilets"](around:{int(radius_m)},{lat},{lon});
  relation["amenity"="toilets"](around:{int(radius_m)},{lat},{lon});
);
out center;"""
    try:
        resp = requests.post(OVERPASS_URL, data=query.encode('utf-8'), headers={**HEADERS, 'Content-Type': 'text/plain; charset=UTF-8'}, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        elements = data.get('elements', [])
        results = []
        for el in elements:
            tags = el.get('tags', {})
            if el['type'] == 'node':
                plat = el.get('lat')
                plon = el.get('lon')
            else:
                center = el.get('center')
                if center:
                    plat = center.get('lat')
                    plon = center.get('lon')
                else:
                    continue
            results.append({
                'id': el.get('id'),
                'type': el.get('type'),
                'lat': plat,
                'lon': plon,
                'tags': tags,
            })
        return results
    except Exception as e:
        return None

class WashroomFinderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Nearest Public Washroom Finder")
        self.geometry("760x520")
        self.resizable(False, False)

        self.create_widgets()

    def create_widgets(self):
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(frm)
        left.grid(row=0, column=0, sticky='ns')

        ttk.Label(left, text="Set your location:").grid(row=0, column=0, sticky='w')

        self.ip_btn = ttk.Button(left, text="Detect via IP", command=self.on_detect_ip)
        self.ip_btn.grid(row=1, column=0, pady=6, sticky='w')

        ttk.Label(left, text="Address:").grid(row=2, column=0, sticky='w')
        self.addr_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.addr_var, width=40).grid(row=3, column=0, sticky='w')
        ttk.Button(left, text="Geocode address", command=self.on_geocode).grid(row=4, column=0, pady=6, sticky='w')

        ttk.Label(left, text="Or enter lat, lon: (decimal)").grid(row=5, column=0, sticky='w', pady=(8,0))
        cfrm = ttk.Frame(left)
        cfrm.grid(row=6, column=0, sticky='w')
        self.lat_var = tk.StringVar()
        self.lon_var = tk.StringVar()
        ttk.Entry(cfrm, textvariable=self.lat_var, width=18).grid(row=0, column=0)
        ttk.Entry(cfrm, textvariable=self.lon_var, width=18).grid(row=0, column=1, padx=(6,0))
        ttk.Button(left, text="Use these coords", command=self.on_use_coords).grid(row=7, column=0, pady=6, sticky='w')

        ttk.Label(left, text="Search radius (meters):").grid(row=8, column=0, sticky='w', pady=(8,0))
        self.radius_var = tk.IntVar(value=1000)
        ttk.Scale(left, from_=100, to=5000, orient=tk.HORIZONTAL, variable=self.radius_var).grid(row=9, column=0, sticky='we')
        ttk.Label(left, textvariable=self.radius_var).grid(row=10, column=0, sticky='w')

        self.search_btn = ttk.Button(left, text="Search Nearby Washrooms", command=self.on_search)
        self.search_btn.grid(row=11, column=0, pady=(12,0), sticky='w')

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(left, textvariable=self.status_var, foreground='gray').grid(row=12, column=0, sticky='w', pady=(8,0))

        right = ttk.Frame(frm)
        right.grid(row=0, column=1, padx=(18,0), sticky='nsew')
        frm.columnconfigure(1, weight=1)

        ttk.Label(right, text="Results:").pack(anchor='w')
        self.results_list = tk.Listbox(right, width=70, height=25)
        self.results_list.pack(fill=tk.BOTH, expand=True)
        self.results_list.bind('<Double-Button-1>', self.on_open_in_map)

        self.info_text = tk.Text(self, height=4, wrap='word')
        self.info_text.pack(fill=tk.X)
        self.info_text.insert(tk.END, "Double-click a result to open in OpenStreetMap.\n")

        self.current_location = None 
        self.last_results = []

    def set_status(self, msg):
        self.status_var.set(msg)

    def on_detect_ip(self):
        self.set_status("Detecting location via IP...")
        self.ip_btn.config(state='disabled')
        threading.Thread(target=self._detect_ip_thread, daemon=True).start()

    def _detect_ip_thread(self):
        res = detect_location_by_ip()
        if res:
            lat, lon, city, region, country = res
            self.current_location = (lat, lon)
            self.lat_var.set(f"{lat:.6f}")
            self.lon_var.set(f"{lon:.6f}")
            info = f"Detected location: {city or ''} {region or ''} {country or ''} ({lat:.6f}, {lon:.6f})"
            self._thread_safe_update(lambda: self.info_text.insert(tk.END, info + "\n"))
            self._thread_safe_update(lambda: self.set_status("Location detected."))
        else:
            self._thread_safe_update(lambda: messagebox.showwarning("IP detect failed", "Could not detect location via IP."))
            self._thread_safe_update(lambda: self.set_status("Ready"))
        self._thread_safe_update(lambda: self.ip_btn.config(state='normal'))

    def on_geocode(self):
        addr = self.addr_var.get().strip()
        if not addr:
            messagebox.showinfo("Address required", "Please type an address to geocode.")
            return
        self.set_status("Geocoding address...")
        threading.Thread(target=self._geocode_thread, args=(addr,), daemon=True).start()

    def _geocode_thread(self, addr):
        res = geocode_address(addr)
        if res:
            lat, lon, display = res
            self.current_location = (lat, lon)
            self.lat_var.set(f"{lat:.6f}")
            self.lon_var.set(f"{lon:.6f}")
            self._thread_safe_update(lambda: self.info_text.insert(tk.END, f"Geocoded: {display} ({lat:.6f}, {lon:.6f})\n"))
            self._thread_safe_update(lambda: self.set_status("Address geocoded."))
        else:
            self._thread_safe_update(lambda: messagebox.showwarning("Geocoding failed", "Could not geocode address."))
            self._thread_safe_update(lambda: self.set_status("Ready"))

    def on_use_coords(self):
        try:
            lat = float(self.lat_var.get())
            lon = float(self.lon_var.get())
        except Exception:
            messagebox.showerror("Invalid coords", "Please enter valid decimal latitude and longitude.")
            return
        self.current_location = (lat, lon)
        self.info_text.insert(tk.END, f"Using manual coords: ({lat:.6f}, {lon:.6f})\n")
        self.set_status("Location set.")

    def on_search(self):
        if not self.current_location:
            messagebox.showinfo("No location", "Please set your location first (detect, geocode, or enter coords).")
            return
        lat, lon = self.current_location
        radius = int(self.radius_var.get())
        self.set_status("Searching Overpass...")
        self.search_btn.config(state='disabled')
        threading.Thread(target=self._search_thread, args=(lat, lon, radius), daemon=True).start()

    def _search_thread(self, lat, lon, radius):
        results = query_overpass(lat, lon, radius)
        if results is None:
            self._thread_safe_update(lambda: messagebox.showerror("Search failed", "Could not query Overpass API."))
            self._thread_safe_update(lambda: self.set_status("Ready"))
            self._thread_safe_update(lambda: self.search_btn.config(state='normal'))
            return
        enriched = []
        for r in results:
            rlat = r['lat']
            rlon = r['lon']
            dist = haversine(lat, lon, rlat, rlon)
            name = r['tags'].get('name') or r['tags'].get('toilets:description') or r['tags'].get('description') or 'Unnamed'
            enriched.append({**r, 'distance_m': dist, 'display_name': name})
        enriched.sort(key=lambda x: x['distance_m'])
        self.last_results = enriched
        self._thread_safe_update(lambda: self._populate_results())
        self._thread_safe_update(lambda: self.set_status(f"Found {len(enriched)} result(s)."))
        self._thread_safe_update(lambda: self.search_btn.config(state='normal'))

    def _populate_results(self):
        self.results_list.delete(0, tk.END)
        if not self.last_results:
            self.results_list.insert(tk.END, "No washrooms found nearby. Try increasing the radius.")
            return
        for r in self.last_results:
            name = r['display_name']
            d = format_distance(r['distance_m'])
            tag_summary = []
            for k in ('access','fee','female','male','unisex','wheelchair'):
                if r['tags'].get(k):
                    tag_summary.append(f"{k}={r['tags'].get(k)}")
            tstr = (", ").join(tag_summary)
            line = f"{name} — {d} — {tstr}"
            self.results_list.insert(tk.END, line)

    def on_open_in_map(self, event):
        sel = self.results_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self.last_results):
            return
        item = self.last_results[idx]
        lat = item['lat']
        lon = item['lon']
        url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=19/{lat}/{lon}"
        webbrowser.open(url)

    def _thread_safe_update(self, fn):
        self.after(0, fn)


if __name__ == '__main__':
    app = WashroomFinderApp()
    app.mainloop()
