import mongoengine, os, sys, datetime

from osgeo import gdal, osr
from osgeo.gdalconst import *  
import models
import struct  

gdal.UseExceptions()
mongoengine.connect("SatelliteImageDatabase")

block_size = 512

models.ImageTile.drop_collection()
models.ImageTileRaster.drop_collection()
models.Image.drop_collection()
models.ImageBand.drop_collection()

def GetExtent(gt,cols,rows):
    ''' Return list of corner coordinates from a geotransform

        @type gt:   C{tuple/list}
        @param gt: geotransform
        @type cols:   C{int}
        @param cols: number of columns in the dataset
        @type rows:   C{int}
        @param rows: number of rows in the dataset
        @rtype:    C{[float,...,float]}
        @return:   coordinates of each corner
    '''
    ext=[]
    xarr=[0,cols]
    yarr=[0,rows]
    for px in xarr:
        for py in yarr:
            x=gt[0]+(px*gt[1])+(py*gt[2])
            y=gt[3]+(px*gt[4])+(py*gt[5])
            ext.append([x,y])
            # print x,y
        yarr.reverse()
    return ext

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

def importBand(bandNumber, imageModel):

    bandImage = models.ImageBand(bandNumber = bandNumber, image = imageModel).save()

    path = os.path.abspath('/host/_Dev/Images/LC80090652013101LGN01/LC80090652013101LGN01_B%i.TIF' % bandNumber)
    ds=gdal.Open(path)

    gt=ds.GetGeoTransform()
    cols = ds.RasterXSize
    rows = ds.RasterYSize
    band = ds.GetRasterBand(1)
    datatype = band.DataType  
    ext=GetExtent(gt,cols,rows)

    src_srs=osr.SpatialReference()
    src_srs.ImportFromWkt(ds.GetProjection())
    tgt_srs=osr.SpatialReference()
    tgt_srs.ImportFromEPSG(4326)
    tgt_srs = src_srs.CloneGeogCS()

    geo_ext=ReprojectCoords(ext,src_srs,tgt_srs)

    pointTL, pointBL, pointBR, pointTR = geo_ext

    blockCols = int(cols / block_size) + 1
    blockRows = int(rows / block_size) + 1

    blockMatrix = [[]]
    pointMatrix = [[]]

    lastBlockSizeX = cols - (blockCols-1)*block_size
    lastBlockSizeY = rows - (blockRows-1)*block_size

    for y in range(0, blockRows+1):
        pointMatrix.append([])
        leftPoint = [(pointBL[0]*(y*block_size) + pointTL[0]*((blockRows-1-y)*block_size+lastBlockSizeY))/rows,
                        (pointBL[1]*(y*block_size) + pointTL[1]*((blockRows-1-y)*block_size+lastBlockSizeY))/rows]
        rightPoint = [(pointBR[0]*(y*block_size) + pointTR[0]*((blockRows-1-y)*block_size+lastBlockSizeY))/rows,
                        (pointBR[1]*(y*block_size) + pointTR[1]*((blockRows-1-y)*block_size+lastBlockSizeY))/rows]
        print '(%s %s)' % (leftPoint, rightPoint)
        # save left point
        pointMatrix[y].append(leftPoint)
        for x in range(blockCols-1, -1, -1):
            point = [(leftPoint[0]*(x*block_size) + rightPoint[0]*((blockCols-1-x)*block_size+lastBlockSizeX))/cols,
                        (leftPoint[1]*(x*block_size) + rightPoint[1]*((blockCols-1-x)*block_size+lastBlockSizeX))/cols]
            
            pointMatrix[y].append(point)
            point = None
        # save right point
        pointMatrix[y].append(rightPoint)

        leftPoint = rightPoint = None

    for y in range(0, blockRows):
        for x in range(0, blockCols):
            xSize = ySize = block_size
            if (x == blockCols-1):
                xSize = cols - x*block_size
            if (y == blockRows-1):
                ySize = rows - y*block_size
            rasterString = band.ReadRaster(x*block_size, y*block_size, xSize, ySize, xSize, ySize, datatype)
            # rasterString = struct.unpack(data_types[gdal.GetDataTypeName(band.DataType)]*xSize*ySize,rasterString)  
            rasterTile = models.ImageTileRaster(raster = rasterString).save()
            models.ImageTile(polygonBorder=[[pointMatrix[y][x],
                                             pointMatrix[y+1][x], 
                                             pointMatrix[y+1][x+1],
                                             pointMatrix[y][x+1],
                                             pointMatrix[y][x]]], 
                            tileRaster = rasterTile,
                            xSize = xSize, ySize = ySize,
                            indexTileX = x, indexTileY = y,
                            band = bandImage).save()
            print "band: %i - add block [%i %i]" % (bandNumber, x, y)
            rasterString = None
            rasterTile = None

    pointMatrix = None
    allTiles = None
    ds = None

    return bandImage

img = models.Image(name = "LC80090652013101LGN01")
img.date = datetime.datetime.strptime("2013-06-04 02:24", "%Y-%m-%d %H:%M")
img.save()

for i in range(1, 12):
    importBand(i, img)
