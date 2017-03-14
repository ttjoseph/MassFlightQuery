# Transliteration of a couple functions from PROJ.4 to JavaScript.
# I have absolutely no idea how any of this works.
from math import atan, tan, sin, cos, acos, floor, ceil
import csv

# Some constants that PROJ uses for the WGS84 ellipse projection.
G_A = 6378137
G_ONEF = 0.99664718933525254
G_FLAT4 = 0.00083820266618686579
G_FLAT64 = 1.756459274006926e-07
METERS_TO_MILES = 0.00062136994949494966
DTOL = 1e-12
SPI = 3.14159265359

# Some 3-letter IATA codes are city codes, which contain multiple airports.
# This is some of them.
AIRPORTS_IN_CITY = {
    'CHI': ['ORD', 'MDW', 'RFD'],
    'NYC': ['LGA', 'JFK', 'EWR', 'HPN'],
    'DFW': ['DFW', 'DAL'],
    'DTT': ['DTW', 'DET', 'YIP'],
    'YEA': ['YEG'],
    'HOU': ['IAH', 'HOU'],
    'QMI': ['MIA', 'FLL', 'PBI'],
    'WAS': ['IAD', 'DCA', 'BWI']
}

CITY_OF_AIRPORT = {}
for (city, airports) in AIRPORTS_IN_CITY.iteritems():
    for airport in airports:
        CITY_OF_AIRPORT[airport] = city

def airport_to_city_code(loc):
    return CITY_OF_AIRPORT[loc] if loc in CITY_OF_AIRPORT else loc

def is_same_place(loc1, loc2):
    """Returns True if loc1 is the same place as loc2, taking into account city codes.
    
    This means, for example:
        is_same_place('LGA', 'EWR') == True
        is_same_place('LGA', 'NYC') == True
    """
    
    loc1, loc2 = loc1.upper(), loc2.upper()
    
    if loc1 == loc2:
        return True
        
    # Generalize the airports to their cities if possible
    loc1 = airport_to_city_code(loc1)
    loc2 = airport_to_city_code(loc2)
    
    # Now convert city code to list of airports
    loc1 = AIRPORTS_IN_CITY[loc1] if loc1 in AIRPORTS_IN_CITY else [loc1]
    loc2 = AIRPORTS_IN_CITY[loc2] if loc2 in AIRPORTS_IN_CITY else [loc2]
    
    any_in = lambda a, b: any(i in b for i in a)
    return any_in(loc1, loc2) or any_in(loc2, loc1)
    

def load_airports_data(fname):
    airports = {}
    with open(fname) as f:
        csvfile = csv.reader(f)
        for row in csvfile:
            # Fields are hardcoded. Yeah, I know. Sorry.
            airports[row[4]] = (float(row[6]), float(row[7]))

    return airports


# Given two latitude/longitude tuples, returns the distance between them using the
# WGS84 projection (which I believe is the IATA standard).
def distance_in_miles(loc1, loc2):
    # This does...something.  Apparently, it's important.
    def adjlon(lon):
        if abs(lon) <= SPI: return lon
        lon += SPI # adjust to 0..2pi rad
        lon -= 2 * SPI * floor(lon / (2 * SPI)) # remove integral # of 'revolutions'
        lon -= SPI # adjust back to -pi..pi rad
        return lon
    
    lat1, lon1 = loc1
    lat2, lon2 = loc2

    # Convert to radians
    lat1 = lat1 * (SPI / 180)
    lat2 = lat2 * (SPI / 180)
    lon1 = lon1 * (SPI / 180)
    lon2 = lon2 * (SPI / 180)
    th1 = atan(G_ONEF * tan(lat1))
    th2 = atan(G_ONEF * tan(lat2))
    thm = .5 * (th1 + th2)
    dthm = .5 * (th2 - th1)
    dlam = adjlon(lon2 - lon1)
    dlamm = .5 * dlam
    geod_S = 0
    if abs(dlam) < DTOL and abs(dthm) < DTOL:
        geod_S = 0.
        return float('nan')
    sindlamm = sin(dlamm)
    costhm = cos(thm)
    sinthm = sin(thm)
    cosdthm = cos(dthm)
    sindthm = sin(dthm)
    L = sindthm * sindthm + (cosdthm * cosdthm - sinthm * sinthm) * sindlamm * sindlamm
    cosd = 1 - L - L
    d = acos(cosd)
    # Holy crap!
    E = cosd + cosd
    sind = sin( d )
    Y = sinthm * cosdthm
    Y *= (Y + Y) / (1. - L)
    T = sindthm * costhm
    T *= (T + T) / L
    X = Y + T
    Y -= T
    T = d / sind
    D = 4. * T * T
    A = D * E
    B = D + D
    geod_S = G_A * sind * (T - G_FLAT4 * (T * X - Y) + \
        G_FLAT64 * (X * (A + (T - .5 * (A - E)) * X) - \
        Y * (B + E * Y) + D * X * Y))
    return geod_S * METERS_TO_MILES
