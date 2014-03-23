from django.shortcuts import render
from django.http import HttpResponse, Http404
from django.core.servers.basehttp import FileWrapper
from django.core.files.temp import NamedTemporaryFile

import hashlib
import shutil, os, datetime, json, mimetypes, settings
from osgeo import gdal, osr
from osgeo.gdalconst import *  
from models import *

def index(request):
	response_dict = {}

	if request.method == 'POST':
		try:
			startDate = datetime.strptime(request.POST['start_date'], "%Y-%m-%d")
			endDate = datetime.strptime(request.POST['end_date'], "%Y-%m-%d")
			ULPoint = map(float, request.POST['ul'].split(','))
			URPoint = map(float, request.POST['ur'].split(','))
			LLPoint = map(float, request.POST['ll'].split(','))
			LRPoint = map(float, request.POST['lr'].split(','))
			bands = map(int, request.POST['bands'].split(','))
		except Exception, e:
			response_dict.update({'error': str(e)})
			return HttpResponse(json.dumps(response_dict), mimetype="application/json")

		imagesQuerySet = Image.objects.filter(date__gt=startDate, date__lt=endDate)

		images_dict = saveImages( request.META['HTTP_HOST'], imagesQuerySet, bands, [[ULPoint, URPoint, LRPoint, LLPoint, ULPoint]])
		response_dict.update({'images':images_dict})
		# response_dict.update({'tile_count': len(allTiles)})
		return HttpResponse(json.dumps(response_dict), mimetype="application/json")

	raise Http404

def downloadImage(request, result_id, band):
	if request.method == 'GET':
		resultImg = QueryResult.objects.filter(pk=result_id).first()
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
					# currentTile.bandRaster[int(band)].raster )

		
		wrapper = FileWrapper(newfile)
		content_type = mimetypes.guess_type(newfile.name)[0]
		response = HttpResponse(wrapper, mimetype='content_type')
		response['Content-Disposition'] = "attachment; filename=%s" % newfile.name
		return response

		# return HttpResponse(json.dumps(response_dict), mimetype="application/json")


def saveImages(hostname, images, bands, polygon):

	images_dict = []

	for imageQuery in images:
		intersectTiles = ImageTile.objects.filter(image=imageQuery, polygonBorder__geo_intersects=polygon).order_by('+indexTileX', '+indexTileY')

		if intersectTiles.count() == 0:
			continue

		qr = QueryResult(tileMatrix = intersectTiles,
						 imageName = imageQuery.name).save()

		for i in bands:
			query_dict = {}
			query_dict.update({'image_name': imageQuery.name})
			query_dict.update({'download_link': hostname + '/download/' + str(qr.id) + '/' + str(i)})
			images_dict.append(query_dict)

	return images_dict


			# finalXSize = topLeftTile.xSize*(colBlock-1) + topRightTile.xSize
			# finalYSize = topLeftTile.ySize*(rowBlock-1) + botLeftTile.ySize
			# normalTileSizeX = topLeftTile.xSize
			# normalTileSizeY = topLeftTile.ySize

			# if finalXSize > finalYSize:
			# 	factor = 150.0 / finalXSize
			# else:
			# 	factor = 150.0 / finalYSize

			# # print '%i %i' % (finalXSize, finalYSize)
			# filename = '%s-band%i.tif' % (imageQuery.name, band.bandNumber)
			# # print 'Export file %s' % filename
			# output_dataset = gtiff.Create(filename, int(finalXSize*factor), int(finalYSize*factor), 1, GDT_UInt16)
			# currentTile = topLeftTile
			# for i in range(0, rowBlock):
			# 	tmpTile = currentTile
			# 	for j in range(0, colBlock):
			# 		# print '\tband %i [%i %i]' % (band.bandNumber, i, j)
			# 		output_dataset.GetRasterBand(1).WriteRaster( 
			# 			int(j*normalTileSizeX*factor), 
			# 			int(i*normalTileSizeY*factor), 
			# 			int(currentTile.xSize*factor), 
			# 			int(currentTile.ySize*factor), 
			# 			currentTile.tileRaster.raster)
			# 		currentTile = currentTile.rightTile
			# 	currentTile = tmpTile.downTile

			# output_dataset = None

