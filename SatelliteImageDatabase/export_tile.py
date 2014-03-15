import models, mongoengine, shutil, os, datetime
from osgeo import gdal
from osgeo.gdalconst import *  

mongoengine.connect("SatelliteImageDatabase")
if (os.path.exists("export")):
	shutil.rmtree("export")
os.mkdir("export")

queryULPoint = [-79, -6.5]
queryURPoint = [-78, -6.5]
queryLLPoint = [-79, -8]
queryLRPoint = [-78, -8]

bands = [1,2,3,4,5,6,7,8,9,10,11]

startTime = datetime.datetime.strptime("2012-3-10 12:00", "%Y-%m-%d %H:%M")
endTime = datetime.datetime.strptime("2014-3-10 12:00", "%Y-%m-%d %H:%M")

imagesQuerySet = models.Image.objects.filter(date__gt=startTime, date__lt=endTime)
allTiles = models.ImageTile.objects.filter(
			polygonBorder__geo_intersects=[[queryULPoint, queryURPoint, queryLRPoint, queryLLPoint, queryULPoint]])

for imageQuery in imagesQuerySet:
	imageBands = [i for i in imageQuery.bands if i.bandNumber in bands]

	for band in imageBands:
		intersectTiles = list(set(band.tiles) & set(allTiles))

		gtiff = gdal.GetDriverByName('GTiff')

		finalXSize = 0
		finalYSize = 0

		# Find the Top Left Tile
		topLeftTile = intersectTiles[0]
		while topLeftTile.leftTile != None and topLeftTile.leftTile in intersectTiles:
			topLeftTile = topLeftTile.leftTile
		while topLeftTile.upTile != None and topLeftTile.upTile in intersectTiles:
			topLeftTile = topLeftTile.upTile

		# print topLeftTile.imageIndex

		colBlock = 1
		# Find the Top Right Tile and number of col blocks
		topRightTile = topLeftTile
		while topRightTile.rightTile != None and topRightTile.rightTile in intersectTiles:
			topRightTile = topRightTile.rightTile
			colBlock = colBlock+1

		rowBlock = 1
		# Find the Bot Left Tile and number of row blocks
		botLeftTile = topLeftTile
		while botLeftTile.downTile != None and botLeftTile.downTile in intersectTiles > 0:
			botLeftTile = botLeftTile.downTile
			rowBlock = rowBlock+1

		finalXSize = topLeftTile.xSize*(colBlock-1) + topRightTile.xSize
		finalYSize = topLeftTile.ySize*(rowBlock-1) + botLeftTile.ySize
		normalTileSizeX = topLeftTile.xSize
		normalTileSizeY = topLeftTile.ySize

		# print '%i %i' % (finalXSize, finalYSize)
		filename = 'export/%s-band%i.tif' % (imageQuery.name, band.bandNumber)
		print 'Export file %s' % filename
		output_dataset = gtiff.Create(filename, finalXSize, finalYSize, 1, GDT_UInt16)
		currentTile = topLeftTile
		for i in range(0, rowBlock):
			tmpTile = currentTile
			for j in range(0, colBlock):
				print '\tband %i [%i %i]' % (band.bandNumber, i, j)
				output_dataset.GetRasterBand(1).WriteRaster( 
					j*normalTileSizeX, 
					i*normalTileSizeY, 
					currentTile.xSize, 
					currentTile.ySize, 
					currentTile.tileRaster.raster )
				currentTile = currentTile.rightTile
			currentTile = tmpTile.downTile

		output_dataset = None