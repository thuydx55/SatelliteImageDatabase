import mongoengine, json, os, csv, re

from models import *

mongoengine.connect("SatelliteImageDatabase", host='localhost', port=27017)

ShapeCountry.drop_collection()
ShapeRegion.drop_collection()
ShapeProvince.drop_collection()
ShapeDistrict.drop_collection()
ShapeCommune.drop_collection()

def process_match(m):
    return unichr(int(m.group(1), 16)).encode('utf-8')

path = os.path.abspath('C:\Users\Nick\Desktop\Vietnam Administration')
path = os.path.abspath('/home/rd320/Desktop/Vietnam Administration')
pattern = '<U\+(.{4})>'

content = open(os.path.join(path, 'VNM_adm0.json')).read()
data = json.loads(content.decode('latin-1').encode('utf-8'))

print 'Import Country'
for ft in data['features']:
    ShapeCountry(
        ISO=ft['properties']['ISO'],
        name=ft['properties']['NAME_ENGLI'],
        shape=ft['geometry']['coordinates']).save()

content = open(os.path.join(path, 'VNM_adm1.json')).read()
data = json.loads(content.decode('latin-1').encode('utf-8'))
reader = list(csv.reader(open(os.path.join(path, 'VNM_adm1.csv'), 'rb')))

print 'Import Region'
for index, ft in enumerate(data['features']):
    country = ShapeCountry.objects.filter(name=re.sub(pattern, process_match, reader[index+1][3])).first()

    if ft['geometry']['type'] == 'MultiPolygon':
        polygons = ft['geometry']['coordinates']
    else:
        polygons = [ft['geometry']['coordinates']]

    ShapeRegion(
        country=country,
        nameVN=re.sub(pattern, process_match, reader[index+1][5]),
        nameEN=ft['properties']['VARNAME_1'],
        shape=polygons).save()

content = open(os.path.join(path, 'VNM_adm2.json')).read()
data = json.loads(content.decode('latin-1').encode('utf-8'))
reader = list(csv.reader(open(os.path.join(path, 'VNM_adm2.csv'), 'rb')))

print 'Import Province'
for index, ft in enumerate(data['features']):
    country = ShapeCountry.objects.filter(name=re.sub(pattern, process_match, reader[index+1][3])).first()
    region = ShapeRegion.objects.filter(nameVN=re.sub(pattern, process_match, reader[index+1][5])).first()

    if ft['geometry']['type'] == 'MultiPolygon':
        polygons = ft['geometry']['coordinates']
    else:
        polygons = [ft['geometry']['coordinates']]

    ShapeProvince(
        country=country,
        region=region,
        nameVN=re.sub(pattern, process_match, reader[index+1][7]),
        nameEN=ft['properties']['VARNAME_2'].split('|')[0],
        typeVN=re.sub(pattern, process_match, reader[index+1][10]),
        typeEN=ft['properties']['ENGTYPE_2'].split('|')[0],
        shape=polygons).save()

content = open(os.path.join(path, 'VNM_adm3.json')).read()
data = json.loads(content.decode('latin-1').encode('utf-8'))
reader = list(csv.reader(open(os.path.join(path, 'VNM_adm3.csv'), 'rb')))

print 'Import District'
for index, ft in enumerate(data['features']):
    province = ShapeProvince.objects.filter(nameVN=re.sub(pattern, process_match, reader[index+1][7])).first()

    if ft['geometry']['type'] == 'MultiPolygon':
        polygons = ft['geometry']['coordinates']
    else:
        polygons = [ft['geometry']['coordinates']]

    ShapeDistrict(
        province=province,
        nameVN=re.sub(pattern, process_match, reader[index+1][9]),
        nameEN=ft['properties']['VARNAME_3'] if ft['properties']['VARNAME_3'] != '' 
                                             else re.sub(pattern, process_match, reader[index+1][9]),
        typeVN=re.sub(pattern, process_match, reader[index+1][12]),
        typeEN=ft['properties']['ENGTYPE_3'],
        shape=polygons).save()

content = open(os.path.join(path, 'VNM_adm4.json')).read()
data = json.loads(content.decode('latin-1').encode('utf-8'))
reader = list(csv.reader(open(os.path.join(path, 'VNM_adm4.csv'), 'rb')))

print 'Import Commune'
for index, ft in enumerate(data['features']):
    province = ShapeProvince.objects.filter(nameVN=re.sub(pattern, process_match, reader[index+1][7])).first()
    district = ShapeDistrict.objects.filter(
                nameVN=re.sub(pattern, process_match, reader[index+1][9]), 
                province=province).first()

    if ft['geometry']['type'] == 'MultiPolygon':
        polygons = ft['geometry']['coordinates']
    else:
        polygons = [ft['geometry']['coordinates']]

    ShapeCommune(
        province=province,
        nameVN=re.sub(pattern, process_match, reader[index+1][11]),
        nameEN=ft['properties']['VARNAME_4'] if ft['properties']['VARNAME_4'] != ''
                                             else re.sub(pattern, process_match, reader[index+1][11]),
        typeVN=ft['properties']['TYPE_4'],
        typeEN=ft['properties']['ENGTYPE_4'],
        shape=polygons).save()