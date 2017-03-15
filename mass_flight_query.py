import requests
import json
import argparse
import sys
import proj4

# You need to enable the QPX Express API in your Google API Manager, and have it generate you an API key,
# which you will put in the below referenced text file
GOOGLE_API_KEY = open('google_api_key.txt').read().strip()
QPX_API_URL = 'https://www.googleapis.com/qpxExpress/v1/trips/search?key=%s' % GOOGLE_API_KEY

def build_flight_query_request(origin, destination, depart_date, return_date=None):
    """Constructs a JSONifiable request structure to send via HTTP POST."""
    req = {}
    req['slice'] = list([{'origin': origin, 'destination': destination, 'date': depart_date}])
    # Look for return flight if caller wants it
    if return_date is not None:
        req['slice'].append({'origin': destination, 'destination': origin, 'date': return_date})

    req['passengers'] = {'adultCount': 1, 'infantInLapCount': 0, 'infantInSeatCount': 0, 'childCount': 0, 'seniorCount': 0}
    req['solutions'] = 20
    req['refundable'] = False

    whole_thing = {}
    whole_thing['request'] = req
    return whole_thing


def parse_airport_list_string(s):
    """Converts a spec of the form 'PHL:3,ORD:2,NYC' that represents the number of people originating
    in a given airport or city into a more computer friendly dict."""
    locs = s.strip().split(',')
    populations = {}
    for loc in locs:
        toks = loc.split(':')
        if len(toks) > 1:
            populations[toks[0]] = int(toks[1])
        else:
            populations[toks[0]] = 1
    return populations
    

def main():
    ap = argparse.ArgumentParser(description="""Makes a bunch of airfare queries at once, or pretty-prints the results.
Uses the QPX Express API from Google and spits results out to a bunch of .json files in the current directory.

Example:

    mass_flight_query.py query --orig PHL:4,MCI:2 --dest STL,LAS,ORD,WDH --depart-date 2018-01-02 --return-date 2018-01-05
    
Then you can postprocess the results, which were put into a bunch of .json files, with something like:

    mass_flight_query.py parse_results --orig PHL:4,MCI:2 --dest STL,LAS,ORD,WDH --depart-date 2018-01-02 --return-date 2018-01-05 --result-files *json
        
It's done this way because QPX Express queries cost 3.5 cents each (!) after the first 50 per day.
So in the postprocessing you can examine some subset of the results without rerunning all the queries.""", formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', type=str, choices=('query', 'parse_results'))
    ap.add_argument('--orig', type=str, help='Comma-separated list of origin 3-character codes (e.g. ORD,NYC)')
    ap.add_argument('--dest', type=str, help='Comma-separated list of destination 3-character codes (e.g. HNL,LAX)')
    ap.add_argument('--depart-date', type=str, help='When to depart (YYYY-MM-DD)')
    ap.add_argument('--return-date', type=str, help='When to return (YYYY-MM-DD)')
    ap.add_argument('--drive-instead', type=float, default=500, help='One-way distance (in miles) below which people would prefer to drive')
    ap.add_argument('--drive-cpm', type=float, default=0.19, help='Cost per mile to drive')
    ap.add_argument('--result-files', type=str, nargs='+', help='Result JSON files to parse')
    ap.add_argument('--dry-run', action='store_true', help='Don\'t actually do the query')
    ap.set_defaults(dry_run=False)
    args = ap.parse_args()

    airports = None
    if args.drive_instead is not None:
        airports = proj4.load_airports_data('airports.dat')

    if args.orig is None or args.dest is None:
        print >>sys.stderr, 'You must specify at least one origin and one destination.'
        return 1

    origins = parse_airport_list_string(args.orig)
    destinations = parse_airport_list_string(args.dest)
    
    if args.command == 'query':
        # Sanity check whether we have enough dates to do the query
        if args.depart_date is None or args.return_date is None:
            print >>sys.stderr, 'You must specify both departure and return dates.'
            return 1
            
        # Query all origin/destination pairs
        for origin in origins:
            for destination in destinations:
                origin = proj4.airport_to_city_code(origin).upper()
                destination = proj4.airport_to_city_code(destination).upper()

                # No need to query for trips that go nowhere
                if proj4.is_same_place(origin, destination): continue 

                if args.drive_instead is not None:
                    dist = proj4.distance_in_miles(airports[proj4.city_code_to_some_airport(origin)],
                        airports[proj4.city_code_to_some_airport(destination)])
                    if dist < args.drive_instead:
                        drive_cost = args.drive_cpm * dist * 2
                        print >>sys.stderr, '%s %s: Drive %.0f miles total ($%.2f)' % (origin, destination, dist*2, drive_cost)
                        continue

                req_data = build_flight_query_request(origin, destination, args.depart_date, args.return_date)
                if args.dry_run is False:
                    r = requests.post(QPX_API_URL, json=req_data)
                    result_json = r.json()
                    print >>sys.stderr, '%s to %s %s %s: %s' % \
                        (origin, destination, args.depart_date, args.return_date, result_json['trips']['tripOption'][0]['saleTotal'])
                    open('%s-%s_%s_%s.json' % (origin, destination, args.depart_date, args.return_date), 'w').write(r.text)
                else:
                    print >>sys.stderr, '%s %s: Did not query because this is a dry run' % (origin, destination)

    elif args.command == 'parse_results':
        # Did the user specify any results to parse?
        if args.result_files is None:
            print >>sys.stderr, 'Please specify some result files to parse, using --result-files.'
            return 1

        # Load the result JSON files
        flights, total_cost = {}, {}
        for result_file in args.result_files:
            with open(result_file) as fp:
                res = json.load(fp)
                # Examine the first flight segment to determine the origin, and the last segment of the first trip
                # to determine the destination
                first_leg = res['trips']['tripOption'][0]['slice'][0]['segment'][0]['leg'][0]
                first_return_leg = res['trips']['tripOption'][0]['slice'][-1]['segment'][0]['leg'][0]
                (origin, destination) = first_leg['origin'], first_return_leg['origin']
                
                # Consider airports equivalent to their city codes if applicable
                # For example, LGA is the same as NYC
                origin = proj4.airport_to_city_code(origin).upper()
                destination = proj4.airport_to_city_code(destination).upper()
                
                # Save this flight info
                key = '%s_%s' % (origin, destination)
                flights[key] = res

        for origin, num_people in origins.iteritems():
            # Normalize airport name to its city code if possible
            origin = proj4.airport_to_city_code(origin).upper()
            for destination in destinations:
                destination = proj4.airport_to_city_code(destination).upper()
                
                # Don't fly to nowhere
                if proj4.is_same_place(origin, destination): continue

                key = '%s_%s' % (origin, destination)

                if destination not in total_cost: total_cost[destination] = 0.0

                # Calculate cost to drive if applicable
                if args.drive_instead is not None:
                    dist = proj4.distance_in_miles(airports[proj4.city_code_to_some_airport(origin)],
                        airports[proj4.city_code_to_some_airport(destination)])
                    if dist < args.drive_instead:
                        drive_cost = args.drive_cpm * dist * 2
                        total_cost[destination] += drive_cost
                        print '%s to %s: Drive %.0f miles total ($%.2f)' % (origin, destination, dist*2, drive_cost)
                        continue
                
                # If we don't have flight pricing data and we aren't driving, then panic a bit, but don't give up
                if key not in flights:
                    print >>sys.stderr, '*** WARNING: Missing flight pricing for %s to %s! ***' % (origin, destination)
                    continue

                res = flights[key]
                sale_total = res['trips']['tripOption'][0]['saleTotal']
                sale_total = float(sale_total[3:])
                total_cost[destination] += sale_total*num_people
                
                # If more than one person is flying, calculate the total fare
                suffix = ' (for %d people, $%.2f)' % (num_people, sale_total*num_people) if num_people > 1 else ''
                print '%s to %s: $%.2f%s' % (origin, destination, sale_total, suffix)
          
        print ''
        # Print results, sorted, with costliest first
        for destination in sorted(total_cost.keys(), key=lambda location: total_cost[location], reverse=True):
            print '%s: $%.2f' % (destination, total_cost[destination])
                

if __name__ == '__main__':
    main()

