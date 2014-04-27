import mongoengine, os, sys, datetime, getopt, re, tarfile

from osgeo import gdal, osr
from osgeo.gdalconst import *  
import models
import struct  

gdal.UseExceptions()
mongoengine.connect("SatelliteImageDatabase", host='localhost', port=27017)

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

def importImage(filename, file_path):

    img = models.Image(name = filename)
    r = re.search('L[COT]8\d{3}\d{3}(\d{4})(\d{3})\w{3}\d\d', filename)
    year = int(r.group(1))
    day_of_year = int(r.group(2))

    img.date = datetime.date(year, 1, 1) + datetime.timedelta(day_of_year - 1)
    img.save()

    pointMatrix = []
    blockMatrix = []

    blockRows = 0
    blockCols = 0

    for i in range(1, 12):
        if i == 8:
            block_size = 512*2
        else:
            block_size = 512

        # path = os.path.abspath('/Volumes/Source/Images/LC80090652013101LGN01/LC80090652013101LGN01_B%i.TIF' % i)
        # path = os.path.abspath('/home/rd320/Landsat8/LC80090652013101LGN01/LC80090652013101LGN01_B%i.TIF' % i)
        path = os.path.join(file_path, filename+'_B%i.TIF' % i)
        ds=gdal.Open(path)

        gt=ds.GetGeoTransform()
        cols = ds.RasterXSize
        rows = ds.RasterYSize
        band = ds.GetRasterBand(1)
        datatype = band.DataType
        # img.projectionBand(update__field__)

        if i == 1:

            # setattr(img, 'projectionBand', ds.GetProjection())
            img.wkt = ds.GetProjection()
            img.save()

            ext=GetExtent(gt,cols,rows)

            pointTL, pointBL, pointBR, pointTR = ext

            blockCols = int(cols / block_size) + 1
            blockRows = int(rows / block_size) + 1

            lastBlockSizeX = cols - (blockCols-1)*block_size
            lastBlockSizeY = rows - (blockRows-1)*block_size

            for y in range(0, blockRows):
                blockMatrix.append([])
                for x in range(0, blockCols):
                    blockMatrix[y].append(models.ImageTile(indexTileX = x, indexTileY = y, image = img).save())

        src_srs=osr.SpatialReference()
        src_srs.ImportFromWkt(ds.GetProjection())
        tgt_srs=osr.SpatialReference()
        tgt_srs.ImportFromEPSG(4326)
        tgt_srs = src_srs.CloneGeogCS()
        transform = osr.CoordinateTransformation( src_srs, tgt_srs)

        for y in range(0, blockRows):
            for x in range(0, blockCols):

                tileModel = blockMatrix[y][x]
                xSize = ySize = block_size
                if (x == blockCols-1):
                    xSize = cols - x*block_size
                if (y == blockRows-1):
                    ySize = rows - y*block_size
                rasterString = band.ReadRaster(x*block_size, y*block_size, xSize, ySize, xSize, ySize, datatype)
                # rasterString = struct.unpack(data_types[gdal.GetDataTypeName(band.DataType)]*xSize*ySize,rasterString)  
                setattr(tileModel, 'band%i' % i, models.ImageTileRaster(raster = rasterString).save())
                tileModel.xSize = xSize
                tileModel.ySize = ySize

                TL = transform.TransformPoint(
                        gt[0] + (x*block_size+0.5)*gt[1] + (y*block_size+0.5)*gt[2],
                        gt[3] + (x*block_size+0.5)*gt[4] + (y*block_size+0.5)*gt[5])
                TL = [TL[0], TL[1]]

                BL = transform.TransformPoint(
                        gt[0] + (x*block_size+0.5)*gt[1] + (y*block_size+ySize+0.5)*gt[2],
                        gt[3] + (x*block_size+0.5)*gt[4] + (y*block_size+ySize+0.5)*gt[5])
                BL = [BL[0], BL[1]]

                BR = transform.TransformPoint(
                        gt[0] + (x*block_size+xSize+0.5)*gt[1] + (y*block_size+ySize+0.5)*gt[2],
                        gt[3] + (x*block_size+xSize+0.5)*gt[4] + (y*block_size+ySize+0.5)*gt[5])
                BR = [BR[0], BR[1]]

                TR = transform.TransformPoint(
                        gt[0] + (x*block_size+xSize+0.5)*gt[1] + (y*block_size+0.5)*gt[2],
                        gt[3] + (x*block_size+xSize+0.5)*gt[4] + (y*block_size+0.5)*gt[5])
                TR = [TR[0], TR[1]]

                tileModel.polygonBorder = [[TL, BL, BR, TR, TL]]

                tileModel.save()

                print "band: %i - add block [%i %i]" % (i, x, y)
                rasterString = None
                rasterTile = None

        ds = None

models.ImageTile.drop_collection()
models.ImageTileRaster.drop_collection()
models.Image.drop_collection()

# log_file = open('log.txt', 'w')


# path = os.path.abspath('/home/rd320/Landsat8')
# des_path = os.path.abspath('/home/rd320/Landsat8-imported')
# files  = os.listdir(path)

# for _file in files:
#     filename = os.path.splitext(_file)[0]
#     filename = os.path.splitext(filename)[0]

#     try:
#         print 'Extract image %s' % os.path.join(path, _file)
#         archive = tarfile.open(os.path.join(path, _file))
#         archive.extractall(os.path.join(path, filename))

#         importImage(filename, os.path.join(path, filename))

#         print 'Remove extracted images'
#         for root, dirs, files in os.walk(os.path.join(path, filename), topdown=False):
#             for name in files:
#                 os.remove(os.path.join(root, name))
#             for name in dirs:
#                 os.rmdir(os.path.join(root, name))
#         os.rmdir(os.path.join(path, filename))

#         os.rename(os.path.join(path, _file), os.path.join(des_path, _file))
#     except Exception, e:
#         log_file.write('%s %s\n' % (_file, e))
#         print '%s %s' % (_file, e)
#         pass
# 
# log_file.close()

# path = os.path.abspath('/Volumes/Source/Images')
path = os.path.abspath('D:\_Dev\Images')

files  = os.listdir(path)
_file = files[0]

filename = os.path.splitext(_file)[0]
filename = os.path.splitext(filename)[0]

print 'Extract image %s' % os.path.join(path, _file)
archive = tarfile.open(os.path.join(path, _file))
archive.extractall(os.path.join(path, filename))

importImage(filename, os.path.join(path, filename))

print 'Remove extracted images'
for root, dirs, files in os.walk(os.path.join(path, filename), topdown=False):
    for name in files:
        os.remove(os.path.join(root, name))
    for name in dirs:
        os.rmdir(os.path.join(root, name))
os.rmdir(os.path.join(path, filename))





#importImage()

# def main(argv):
#     inputfile = ''
#     outputfile = ''
#     try:
#         opts, args = getopt.getopt(argv,"hi:o:",["ifile=","ofile="])
#     except getopt.GetoptError:
#         print os.path.basename(__file__), ' -i <inputfile> -o <outputfile>'
#         sys.exit(2)
#     for opt, arg in opts:
#         if opt == '-h':
#             print os.path.basename(__file__), ' -i <inputfile> -o <outputfile>'
#             sys.exit()
#         elif opt in ("-i", "--ifile"):
#             inputfile = arg
#         elif opt in ("-o", "--ofile"):
#             outputfile = arg
#     print 'Input file is "', inputfile
#     print 'Output file is "', outputfile

# if __name__ == "__main__":
#    main(sys.argv[1:])