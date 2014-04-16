from django.shortcuts import render
from django.http import HttpResponse, Http404
from django.core.servers.basehttp import FileWrapper
from django.core.files.temp import NamedTemporaryFile

import hashlib
import shutil, os, datetime, json, mimetypes, settings
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
			# ULPoint = map(float, request.POST['ul'].split(','))
			# URPoint = map(float, request.POST['ur'].split(','))
			# LLPoint = map(float, request.POST['ll'].split(','))
			# LRPoint = map(float, request.POST['lr'].split(','))
			inputPolygon = eval(request.POST['polygon'])
			bands = map(int, request.POST['bands'].split(','))
		except Exception, e:
			response_dict.update({'error': str(e)})
			return HttpResponse(json.dumps(response_dict), mimetype="application/json")

		imagesQuerySet = models.Image.objects.filter(date__gt=startDate, date__lt=endDate)

		
		images_dict = queryImages(imagesQuerySet, bands, inputPolygon)
		response_dict.update({'images':images_dict})

		# response_dict.update({'tile_count': len(allTiles)})
		return HttpResponse(json.dumps(dict(images=images_dict)), mimetype="application/json")

	raise Http404

def queryImages(images, bands, inputPolygon):

	ULx = LRx = inputPolygon[0][0]
	ULy = LRy = inputPolygon[0][1]

	for x, y in inputPolygon:
		if x > LRx:
			LRx = x
		if x < ULx:
			ULx = x
		if y > ULy:
			ULy = y
		if y < LRy:
			LRy = y
	query_polygon = [[ULx, ULy], [ULx, LRy], [LRx, LRy], [LRx, ULy], [ULx, ULy]]

	if inputPolygon[0] != inputPolygon[len(inputPolygon)-1]:
		inputPolygon.append(inputPolygon[0])

	images_dict = []

	for imageQuery in images:
		intersectTiles = models.ImageTile.objects.filter(image=imageQuery, polygonBorder__geo_intersects=[query_polygon]).order_by('+indexTileX', '+indexTileY')

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

		newfile = NamedTemporaryFile(suffix='.tif', prefix=resultImg.imageName+'-'+str(band))

		firstTile, lastTile = tiles[0], tiles[len(tiles)-1]

		xBlock = lastTile.indexTileX - firstTile.indexTileX + 1
		yBlock = lastTile.indexTileY - firstTile.indexTileY + 1

		finalXSize = firstTile.getXSize(band) * (xBlock-1) + lastTile.getXSize(band)
		finalYSize = firstTile.getYSize(band) * (yBlock-1) + lastTile.getYSize(band)

		gtiff = gdal.GetDriverByName('GTiff')

		output_dataset = gtiff.Create(newfile.name, finalXSize, finalYSize, 1, GDT_UInt16)

		for y in range(0, yBlock):
			for x in range(0, xBlock):
				currentTile = tiles[x*yBlock+y]

				output_dataset.GetRasterBand(1).WriteRaster( 
					x*firstTile.getXSize(band), 
					y*firstTile.getYSize(band), 
					currentTile.getXSize(band), 
					currentTile.getYSize(band), 
					getattr(currentTile, 'band%s' % band).raster)
		
		outputImageBorder = [tiles[0].polygonBorder['coordinates'][0][0], 
							tiles[yBlock-1].polygonBorder['coordinates'][0][1],
							tiles[(xBlock-1)*yBlock+yBlock-1].polygonBorder['coordinates'][0][2],
							tiles[(xBlock-1)*yBlock].polygonBorder['coordinates'][0][3]]

		src_srs=osr.SpatialReference()
        src_srs.ImportFromWkt(tiles[0].image.wkt)
        tgt_srs=osr.SpatialReference()
        tgt_srs.ImportFromEPSG(4326)
        tgt_srs = src_srs.CloneGeogCS()

        ext=ReprojectCoords(outputImageBorder, tgt_srs, src_srs)

        xPix = (round(ext[2][0])-round(ext[0][0]))/finalXSize
        yPix = (round(ext[2][1])-round(ext[0][1]))/finalYSize

        origin_point = [round(ext[0][0])+xPix/2, round(ext[0][1])- yPix/2]

        output_geo_transform = [origin_point[0], xPix, 0, origin_point[1], 0, yPix]

        ds = gdal.Open(newfile.name, gdal.GA_Update)
        ds.SetGeoTransform(output_geo_transform)
        ds.SetProjection(src_srs.ExportToWkt())

        # Clip Image
        pixels = []
        inputPolygonReprojected = ReprojectCoords(resultImg.inputPolygon['coordinates'][0], tgt_srs, src_srs)
        for p in inputPolygonReprojected:
  			pixels.append(world2Pixel(output_geo_transform, p[0], p[1]))

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

        ULx, ULy = world2Pixel(output_geo_transform, ULx, ULy)
        LRx, LRy = world2Pixel(output_geo_transform, LRx, LRy)

        clip = output_dataset.GetRasterBand(1).ReadAsArray(0, 0, finalXSize, finalYSize)[ULy:LRy, ULx:LRx]
        
        pxWidth = int(LRx - ULx)
        pxHeight = int(LRy - ULy)

        rasterPoly = Image.new("L", (pxWidth, pxHeight), 1)
        rasterize = ImageDraw.Draw(rasterPoly)
        rasterize.polygon(pixels, 0)

        mask = imageToArray(rasterPoly)

		# Clip the image using the mask
        clip = gdalnumeric.choose(mask, (clip, 0)).astype(gdalnumeric.uint16)
        
        gdalnumeric.SaveArray(clip, "%s.tif" % 'output', format="GTiff")

 	
 		# Return HttpResponse Image
        wrapper = FileWrapper(newfile)
        content_type = mimetypes.guess_type(newfile.name)[0]
        response = HttpResponse(wrapper, mimetype='content_type')
        response['Content-Disposition'] = "attachment; filename=%s" % newfile.name

        return response

        # return HttpResponse(json.dumps(dict(out=output_geo_transform,
        # 	ext=ext,
        # 	finalXSize=finalXSize,
        # 	finalYSize=finalYSize)))
		


	raise Http404


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