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

gdal.UseExceptions()



def index(request):
    response_dict = {}

    if request.method == 'POST':
        try:
            startDate = datetime.datetime.strptime(request.POST['start_date'], "%Y-%m-%d")
            endDate = datetime.datetime.strptime(request.POST['end_date'], "%Y-%m-%d")
            inputPolygon = eval(request.POST['polygon'])
            bands = map(int, request.POST['bands'].split(','))
        except Exception, e:
            response_dict.update({'error': str(e)})
            return HttpResponse(json.dumps(response_dict), content_type="application/json")

        imagesQuerySet = models.Image.objects.filter(date__gt=startDate, date__lt=endDate)

        
        images_dict = queryImages(imagesQuerySet, bands, inputPolygon)
        response_dict.update({'images':images_dict})

        # response_dict.update({'tile_count': len(allTiles)})
        return HttpResponse(json.dumps(dict(images=images_dict)), content_type="application/json")

    raise Http404

def queryImages(images, bands, inputPolygon):

    if inputPolygon[0] != inputPolygon[len(inputPolygon)-1]:
        inputPolygon.append(inputPolygon[0])

    images_dict = []

    for imageQuery in images:
        intersectTiles = models.ImageTile.objects.filter(image=imageQuery, polygonBorder__geo_intersects=[inputPolygon])

        if intersectTiles.count() == 0:
            continue

        qr = models.QueryResult(tileMatrix = intersectTiles,
                                 imageName = imageQuery.name,
                                 inputPolygon=[inputPolygon]).save()

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
        print preClipGeoTransform

        pixels = []
        inputPolygonReprojected = ReprojectCoords(resultImg.inputPolygon['coordinates'][0], tgt_srs, src_srs)
        for p in inputPolygonReprojected:
            pixels.append(world2Pixel(preClipGeoTransform, p[0], p[1]))

        pixels = intersectPolygonToBorder(pixels, preClipSize[0], preClipSize[1])

        ULx = LRx = inputPolygonReprojected[0][0]
        ULy = LRy = inputPolygonReprojected[0][1]

        for x, y in inputPolygonReprojected:
            if x > LRx:
                LRx = x
            if x < ULx:
                ULx = x
            if y > ULy:
                ULy = y
            if y < LRy:
                LRy = y

        ULx, ULy = world2Pixel(preClipGeoTransform, ULx, ULy)
        LRx, LRy = world2Pixel(preClipGeoTransform, LRx, LRy)

        ULx = 0 if ULx < 0 else ULx
        LRx = 0 if LRx < 0 else LRx
        ULy = 0 if ULy < 0 else ULy
        LRy = 0 if LRy < 0 else LRy

        # clipped the output dataset by minimum rect
        clip = preClipDS.GetRasterBand(1).ReadAsArray(0, 0, preClipSize[0], preClipSize[1])[ULy:LRy, ULx:LRx]

        rasterPoly = Image.new("L", (preClipSize[0], preClipSize[1]), 1)
        rasterize = ImageDraw.Draw(rasterPoly)
        rasterize.polygon(pixels, 0)

        # create mask to clip image by polygon
        mask = imageToArray(rasterPoly)[ULy:LRy, ULx:LRx]

        # Clip the image using the mask
        clip = gdalnumeric.choose(mask, (clip, 0)).astype(gdalnumeric.uint16)

        finalFile = NamedTemporaryFile(suffix='.tif', prefix=resultImg.imageName+'-'+str(band))
        gdalnumeric.SaveArray(clip, str(finalFile.name) , format="GTiff")
        
        ds = gdal.Open(str(finalFile.name), gdal.GA_Update)
        ds.SetGeoTransform(preClipGeoTransform)
        ds.SetProjection(src_srs.ExportToWkt())


        # for y in range(0, yBlock):
        #     for x in range(0, xBlock):
        #         currentTile = tiles[x*yBlock+y]
        #         while not (len(tiles) > 0 and currentTile.indexTileX-diffX == x and currentTile.indexTileY-diffY == y):
        #             tiles.remove(currentTile)
        #             currentTile = tiles[x*yBlock+y]

        #         output_dataset.GetRasterBand(1).WriteRaster( 
        #             x*firstTile.getXSize(band), 
        #             y*firstTile.getYSize(band), 
        #             currentTile.getXSize(band), 
        #             currentTile.getYSize(band), 
        #             getattr(currentTile, 'band%s' % band).raster)
        
        # outputImageBorder = [tiles[0].polygonBorder['coordinates'][0][0], 
        #                     tiles[yBlock-1].polygonBorder['coordinates'][0][1],
        #                     tiles[(xBlock-1)*yBlock+yBlock-1].polygonBorder['coordinates'][0][2],
        #                     tiles[(xBlock-1)*yBlock].polygonBorder['coordinates'][0][3]]

        # src_srs=osr.SpatialReference()
        # src_srs.ImportFromWkt(tiles[0].image.wkt)
        # tgt_srs=osr.SpatialReference()
        # tgt_srs.ImportFromEPSG(4326)
        # tgt_srs = src_srs.CloneGeogCS()

        # ext=ReprojectCoords(outputImageBorder, tgt_srs, src_srs)

        # xPix = (round(ext[2][0])-round(ext[0][0]))/finalXSize
        # yPix = (round(ext[2][1])-round(ext[0][1]))/finalYSize

        # origin_point = [round(ext[0][0])+xPix/2, round(ext[0][1])- yPix/2]

        # output_geo_transform = [origin_point[0], xPix, 0, origin_point[1], 0, yPix]

        # # Clip Image0
        # pixels = []
        # inputPolygonReprojected = ReprojectCoords(resultImg.inputPolygon['coordinates'][0], tgt_srs, src_srs)
        # for p in inputPolygonReprojected:
        #     pixels.append(world2Pixel(output_geo_transform, p[0], p[1]))

        # pixels = intersectPolygonToBorder(pixels, finalXSize, finalYSize)

        #   # Get the Upper-Left and Lower-Right point of minimum rectagle that contains input polygon
        # ULx = LRx = inputPolygonReprojected[0][0]
        # ULy = LRy = inputPolygonReprojected[0][1]

        # for x, y in inputPolygonReprojected:
        #     if x > LRx:
        #         LRx = x
        #     if x < ULx:
        #         ULx = x
        #     if y > ULy:
        #         ULy = y
        #     if y < LRy:
        #         LRy = y

        # ULx, ULy = world2Pixel(output_geo_transform, ULx, ULy)
        # LRx, LRy = world2Pixel(output_geo_transform, LRx, LRy)

        # ULx = 0 if ULx < 0 else ULx
        # LRx = 0 if LRx < 0 else LRx
        # ULy = 0 if ULy < 0 else ULy
        # LRy = 0 if LRy < 0 else LRy

        # # clipped the output dataset by minimum rect
        # clip = output_dataset.GetRasterBand(1).ReadAsArray(0, 0, finalXSize, finalYSize)[ULy:LRy, ULx:LRx]

        # rasterPoly = Image.new("L", (finalXSize, finalYSize), 1)
        # rasterize = ImageDraw.Draw(rasterPoly)
        # rasterize.polygon(pixels, 0)

        # # create mask to clip image by polygon
        # mask = imageToArray(rasterPoly)[ULy:LRy, ULx:LRx]

        # # Clip the image using the mask
        # clip = gdalnumeric.choose(mask, (clip, 0)).astype(gdalnumeric.uint16)
        # # clip = clip[ULy:LRy, ULx:LRx]
        
        # finalFile = NamedTemporaryFile(suffix='.tif', prefix=resultImg.imageName+'-'+str(band))
        # gdalnumeric.SaveArray(clip, str(finalFile.name) , format="GTiff")
        
        # ds = gdal.Open(str(finalFile.name), gdal.GA_Update)
        # ds.SetGeoTransform(output_geo_transform)
        # ds.SetProjection(src_srs.ExportToWkt())

     
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





