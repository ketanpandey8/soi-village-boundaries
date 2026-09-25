#!/usr/bin/env python3
"""Write dist/data/states.json from the per-state geojson files, with clean names."""
import os, json
D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist", "data")
NAMES = {
 "andaman-nicobar-islands":"Andaman & Nicobar Islands","andhra-pradesh":"Andhra Pradesh",
 "bihar":"Bihar","chandigarh":"Chandigarh","chhattisgarh":"Chhattisgarh",
 "dadra-nagar-haveli-daman-diu":"Dadra & Nagar Haveli & Daman & Diu","delhi":"Delhi",
 "goa":"Goa","gujarat":"Gujarat","haryana":"Haryana","jharkhand":"Jharkhand",
 "karnataka":"Karnataka","kerala":"Kerala","lakshadweep":"Lakshadweep",
 "madhya-pradesh":"Madhya Pradesh","maharashtra":"Maharashtra","odisha":"Odisha",
 "puducherry":"Puducherry","punjab":"Punjab","rajasthan":"Rajasthan","sikkim":"Sikkim",
 "tamil-nadu":"Tamil Nadu","telangana":"Telangana","tripura":"Tripura",
 "uttar-pradesh":"Uttar Pradesh","uttarakhand":"Uttarakhand","west-bengal":"West Bengal",
}
m = []
for f in sorted(os.listdir(D)):
    if not f.endswith(".geojson") or f == "india.geojson": continue
    slug = f[:-8]
    m.append({"slug": slug, "name": NAMES.get(slug, slug.replace("-", " ").title())})
m.sort(key=lambda x: x["name"])
json.dump(m, open(os.path.join(D, "states.json"), "w"))
print(f"{len(m)} states -> states.json")
for x in m: print(" ", x["name"])
