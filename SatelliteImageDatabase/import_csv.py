import csv, mongoengine, os, re

mongoengine.connect("SatelliteImageDatabase", host='localhost', port=27017)

class Test(mongoengine.Document):
    s = mongoengine.StringField()

def process_match(m):
    return unichr(int(m.group(1), 16)).encode('utf-8')

Test.drop_collection()

path = os.path.abspath('C:\Users\Nick\Desktop\Vietnam Administration')
pattern = '<U\+(.{4})>'

with open(os.path.join(path, 'VNM_adm2.csv'), 'rb') as csvfile:
    r = csv.reader(csvfile)
    for row in r:

        # Test(s=re.sub(pattern, unichr(int(r'\1', 16)).encode('utf-8'), ', '.join(row))).save()
        Test(s=re.sub(pattern, process_match, ', '.join(row))).save()
        # Test(s=', '.join(row)).save()