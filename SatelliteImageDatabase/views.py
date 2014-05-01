from django.shortcuts import render
from django.http import HttpResponse, Http404, StreamingHttpResponse
from django.core.servers.basehttp import FileWrapper
from django.core.files.temp import NamedTemporaryFile

import hashlib
import shutil, os, datetime, json, mimetypes, settings, ast
from osgeo import gdal, gdalnumeric, ogr, osr
from PIL import Image, ImageDraw
from osgeo.gdalconst import *  
import models
from mongoengine import Q

gdal.UseExceptions()



def index(request):
    response_dict = {}

    if request.method == 'POST':
        try:
            startDate = datetime.datetime.strptime(request.POST['start_date'], "%Y-%m-%d")
            endDate = datetime.datetime.strptime(request.POST['end_date'], "%Y-%m-%d")
            bands = map(int, request.POST['bands'].split(','))
        except Exception, e:
            response_dict.update({'error': str(e)})
            return HttpResponse(json.dumps(response_dict), content_type="application/json")

        imagesQuerySet = models.Image.objects.filter(date__gt=startDate, date__lt=endDate)

        inputPolygons = None
        if 'polygons' in request.POST:
            inputPolygons = eval(request.POST['polygons'])
        if 'provinceid' in request.POST:
            p = models.ShapeProvince.objects.filter(id=request.POST['provinceid']).first()
            if p is None:
                return HttpResponse(json.dumps(dict(status='failed', error='Province not found')), content_type="application/json")
            inputPolygons = [polygon['coordinates'][0] for polygon in p.shape]
        if 'districtid' in request.POST:
            d = models.ShapeDistrict.objects.filter(id=request.POST['districtid']).first()
            if d is None:
                return HttpResponse(json.dumps(dict(status='failed', error='District not found')), content_type="application/json")
            inputPolygons = [polygon['coordinates'][0] for polygon in d.shape]
        if 'communeid' in request.POST:
            c = models.ShapeDistrict.objects.filter(id=request.POST['communeid']).first()
            if c is None:
                return HttpResponse(json.dumps(dict(status='failed', error='Commune not found')), content_type="application/json")
            inputPolygons = [polygon['coordinates'][0] for polygon in c.shape]
        if 'province' in request.POST:
            p = models.ShapeProvince.objects.filter(nameEN=request.POST['province']).first()
            if p is None:
                return HttpResponse(json.dumps(dict(status='failed', error='Province not found')), content_type="application/json")
            inputPolygons = [polygon['coordinates'][0] for polygon in p.shape]
        if 'district' in request.POST:
            d = models.ShapeDistrict.objects.filter(nameEN=request.POST['district']).first()
            if d is None:
                return HttpResponse(json.dumps(dict(status='failed', error='District not found')), content_type="application/json")
            inputPolygons = [polygon['coordinates'][0] for polygon in d.shape]
        if 'commune' in request.POST:
            c = models.ShapeDistrict.objects.filter(nameEN=request.POST['commune']).first()
            if c is None:
                return HttpResponse(json.dumps(dict(status='failed', error='Commune not found')), content_type="application/json")
            inputPolygons = [polygon['coordinates'][0] for polygon in c.shape]


        images_dict = queryImages(imagesQuerySet, bands, inputPolygons)
        response_dict.update({'images':images_dict})

        # response_dict.update({'tile_count': len(allTiles)})
        return HttpResponse(json.dumps(dict(images=images_dict)), content_type="application/json")

    raise Http404

def queryImages(images, bands, inputPolygons):

    queryPolygons = []

    for p in inputPolygons:
        # if p[0] != p[len(p)-1]:
        #     p.append(p[0])
        mostLeft = mostRight = p[0][0]
        mostTop = mostBot = p[0][1]
        for pp in p:
            if mostLeft > pp[0]:
                mostLeft = pp[0]
            if mostRight < pp[0]:
                mostRight = pp[0]
            if mostTop < pp[0]:
                mostTop = pp[0]
            if mostBot > pp[0]:
                mostBot = pp[0]

        queryPolygons.append([
            [mostLeft, mostTop],
            [mostLeft, mostBot], 
            [mostRight, mostBot], 
            [mostRight, mostTop], 
            [mostLeft, mostTop]])

    images_dict = []

    for imageQuery in images:
        args = Q()
        for p in queryPolygons:
            args = args | Q(polygonBorder__geo_intersects=[p])

        imageTileQS = models.ImageTile.objects.filter(image=imageQuery)
        intersectTiles = imageTileQS.filter(args)

        if intersectTiles.count() == 0:
            continue

        qr = models.QueryResult(tileMatrix = intersectTiles,
                                 imageName = imageQuery.name,
                                 inputPolygons=[[p] for p in inputPolygons]).save()

        for i in bands:
            query_dict = {}
            query_dict.update({'image_name': imageQuery.name})
            query_dict.update({'download_link': '/download/' + str(qr.id) + '/' + str(i)})
            images_dict.append(query_dict)

    return images_dict


def downloadImage(request, result_id, band):
    if request.method == 'GET':
        resultImg = models.QueryResult.objects.filter(pk=result_id).first()
        if resultImg == None:
            raise Http404 

        tiles = list(resultImg.tileMatrix)

        src_srs=osr.SpatialReference()
        src_srs.ImportFromWkt(tiles[0].image.wkt)
        tgt_srs=osr.SpatialReference()
        tgt_srs.ImportFromEPSG(4326)
        tgt_srs = src_srs.CloneGeogCS()

        preClipDS, preClipSize, preClipGeoTransform = GetPreClipImage(tiles, band, resultImg.imageName, src_srs, tgt_srs)
        # print preClipGeoTransform

        # Raster of input polygons
        rasterPoly = Image.new("L", (preClipSize[0], preClipSize[1]), 1)
        rasterize = ImageDraw.Draw(rasterPoly)

        inputPolygons = resultImg.inputPolygons

        mostULx = mostLRx = mostULy = mostLRy = None

        for polygon in inputPolygons:
            pixels = []
            inputPolygonReprojected = ReprojectCoords(polygon['coordinates'][0], tgt_srs, src_srs)
            for p in inputPolygonReprojected:
                pixels.append(world2Pixel(preClipGeoTransform, p[0], p[1]))

            pixels = intersectPolygonToBorder(pixels, preClipSize[0], preClipSize[1])
            
            print pixels

            if mostULx == None or   \
                mostLRx == None or  \
                mostULy == None or  \
                mostLRy == None:
                
                mostULx = mostLRx = pixels[0][0]
                mostULy = mostLRy = pixels[0][1]

            for x, y in pixels:
                if x > mostLRx:
                    mostLRx = x
                if x < mostULx:
                    mostULx = x
                if y < mostULy:
                    mostULy = y
                if y > mostLRy:
                    mostLRy = y

            # mostULx, mostULy = world2Pixel(preClipGeoTransform, mostULx, mostULy)
            # mostLRx, mostLRy = world2Pixel(preClipGeoTransform, mostLRx, mostLRy)

            mostULx = 0 if mostULx < 0 else mostULx
            mostLRx = 0 if mostLRx < 0 else mostLRx
            mostULy = 0 if mostULy < 0 else mostULy
            mostLRy = 0 if mostLRy < 0 else mostLRy

            rasterize.polygon(pixels, 0)

        print '%i %i %i %i' % (mostULx, mostULy, mostLRx, mostLRy)

        # clipped the output dataset by minimum rect
        clip = preClipDS.GetRasterBand(1).ReadAsArray(0, 0, preClipSize[0], preClipSize[1])[mostULy:mostLRy, mostULx:mostLRx]

        # create mask to clip image by polygon
        mask = imageToArray(rasterPoly)[mostULy:mostLRy, mostULx:mostLRx]

        # Clip the image using the mask
        clip = gdalnumeric.choose(mask, (clip, 0)).astype(gdalnumeric.uint16)

        finalFile = NamedTemporaryFile(suffix='.tif', prefix=resultImg.imageName+'-'+str(band))
        gdalnumeric.SaveArray(clip, str(finalFile.name) , format="GTiff")

        clippedGeoTransform = [preClipGeoTransform[0] + mostULx*preClipGeoTransform[1],
                                preClipGeoTransform[1],
                                preClipGeoTransform[2],
                                preClipGeoTransform[3] + mostULy*preClipGeoTransform[5],
                                preClipGeoTransform[4],
                                preClipGeoTransform[5]]
        
        ds = gdal.Open(str(finalFile.name), gdal.GA_Update)
        ds.SetGeoTransform(clippedGeoTransform)
        ds.SetProjection(src_srs.ExportToWkt())
     
         # Return HttpResponse Image
        wrapper = FileWrapper(finalFile)
        content_type = mimetypes.guess_type(finalFile.name)[0]
        response = StreamingHttpResponse(wrapper, content_type='content_type')
        response['Content-Disposition'] = "attachment; filename=%s" % finalFile.name

        return response

        # return HttpResponse(json.dumps(dict(out=output_geo_transform,
        #     ext=ext,
        #     finalXSize=finalXSize,
        #     finalYSize=finalYSize)))
        


    raise Http404

def GetPreClipImage(tiles, band, name, src_srs, tgt_srs):
    blockSize = 512
    if band == 8:
        blockSize = 1024 
    
    preClipImage = NamedTemporaryFile(suffix='.tif', prefix=name+'-'+str(band))

    maxTileIndexX = minTileIndexX = tiles[0].indexTileX
    maxTileIndexY = minTileIndexY = tiles[0].indexTileY

    botTile = rightTile = tiles[0]

    for tile in tiles:
        if tile.indexTileX > maxTileIndexX:
            maxTileIndexX = tile.indexTileX
            rightTile = tile

        if tile.indexTileX < minTileIndexX:
            minTileIndexX = tile.indexTileX

        if tile.indexTileY > maxTileIndexY:
            maxTileIndexY = tile.indexTileY
            botTile = tile

        if tile.indexTileY < minTileIndexY:
            minTileIndexY = tile.indexTileY

    preClipSizeX = (maxTileIndexX - minTileIndexX)*blockSize + rightTile.getXSize(band)
    preClipSizeY = (maxTileIndexY - minTileIndexY)*blockSize + botTile.getYSize(band)

    gtiff = gdal.GetDriverByName('GTiff')
    output_dataset = gtiff.Create(str(preClipImage.name), preClipSizeX, preClipSizeY, 1, GDT_UInt16)

    for tile in tiles:
        output_dataset.GetRasterBand(1).WriteRaster(
            (tile.indexTileX - minTileIndexX)*blockSize,
            (tile.indexTileY - minTileIndexY)*blockSize,
            tile.getXSize(band),
            tile.getYSize(band),
            getattr(tile, 'band%s' % band).raster)

    botTilePolygon = botTile.polygonBorder['coordinates'][0]
    botTileUL, botTileLR = botTilePolygon[0], botTilePolygon[2]

    transform = osr.CoordinateTransformation( tgt_srs, src_srs)
    x,y,z = transform.TransformPoint(botTileUL[0], botTileUL[1])
    botTileUL = [round(x), round(y)]
    x,y,z = transform.TransformPoint(botTileLR[0], botTileLR[1])
    botTileLR = [round(x), round(y)]

    xPix = (botTileLR[0]-botTileUL[0])/botTile.getXSize(band)
    yPix = (botTileLR[1]-botTileUL[1])/botTile.getYSize(band)

    imageUL = [botTileUL[0] - (botTile.indexTileX - minTileIndexX) * blockSize * xPix,
                botTileUL[1] - (botTile.indexTileY - minTileIndexY) * blockSize * yPix]

    return output_dataset, \
            [preClipSizeX, preClipSizeY], \
            [imageUL[0], xPix, 0, imageUL[1], 0, yPix]


def ReprojectCoords(coords,src_srs,tgt_srs):
    ''' Reproject a list of x,y coordinates.

        @type geom:     C{tuple/list}
        @param geom:    List of [[x,y],...[x,y]] coordinates
        @type src_srs:  C{osr.SpatialReference}
        @param src_srs: OSR SpatialReference object
        @type tgt_srs:  C{osr.SpatialReference}
        @param tgt_srs: OSR SpatialReference object
        @rtype:         C{tuple/list}
        @return:        List of transformed [[x,y],...[x,y]] coordinates
    '''
    trans_coords=[]
    transform = osr.CoordinateTransformation( src_srs, tgt_srs)
    for x,y in coords:
        x,y,z = transform.TransformPoint(x,y)
        trans_coords.append([x,y])
    return trans_coords

def world2Pixel(geoMatrix, x, y):
    """
    Uses a gdal geomatrix (gdal.GetGeoTransform()) to calculate
    the pixel location of a geospatial coordinate 
    """
    ulX = geoMatrix[0]
    ulY = geoMatrix[3]
    xDist = geoMatrix[1]
    yDist = geoMatrix[5]
    rtnX = geoMatrix[2]
    rtnY = geoMatrix[4]
    pixel = int((x - ulX) / xDist)
    line = int((ulY - y) / xDist)
    return (pixel, line) 

def imageToArray(i):
    """
    Converts a Python Imaging Library array to a 
    gdalnumeric image.
    """
    a=gdalnumeric.fromstring(i.tostring(),'b')
    a.shape=i.im.size[1], i.im.size[0]
    return a

def intersectPolygonToBorder(pixel_polygon, xSize, ySize):
    polygon = []
    for pp in pixel_polygon:
        polygon.append([pp[0],pp[1]])

    polygonJson = { "type": "Polygon", "coordinates": [polygon] }
    polygonGeo = ogr.CreateGeometryFromJson(str(polygonJson))

    border = [[0,0],[xSize, 0],[xSize,ySize],[0,ySize],[0,0]]
    borderJson = { "type": "Polygon", "coordinates": [border] }
    borderGeo = ogr.CreateGeometryFromJson(str(borderJson))

    intersectedGeo = polygonGeo.Intersection(borderGeo)
    intersected = ast.literal_eval(intersectedGeo.ExportToJson())

    pixel_intersected = []
    for pi in intersected['coordinates'][0]:
        pixel_intersected.append((pi[0],pi[1]))

    return pixel_intersected





