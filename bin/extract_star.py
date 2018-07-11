#! /usr/bin/env python
# -*- coding: utf-8 -*-



MARKER_PROP = {"astrom": dict(marker="x", lw=2, s=80, color="C1", zorder=8),
               "manual": dict(marker="+", lw=2, s=100, color="k", zorder=8),
               "auto":  dict(marker="o", lw=2, s=200, facecolors="None", edgecolors="C3", zorder=8)
                   }


def position_source(cube, centroid=None, centroiderr=None):
    """ How is the source position selected ? """
    if centroiderr is None or centroiderr in ["None"]:
        centroid_err_given = False
        centroids_err = [3,3]
    else:
        centroid_err_given = True
        centroids_err = np.asarray(centroiderr, dtype="float")
        
    if centroid is None or centroid in ["None"]:
        from pysedm.astrometry  import get_object_ifu_pos
        xcentroid,ycentroid = get_object_ifu_pos( cube )
        if np.isnan(xcentroid*ycentroid):
            print("IFU target location based on CCD astrometry failed. centroid guessed based on brightness used instead")
            sl = cube.get_slice(lbda_min=lbdaranges[0], lbda_max=lbdaranges[1], slice_object=True)
            x,y = np.asarray(sl.index_to_xy(sl.indexes)).T # Slice x and y
            argmaxes = np.argwhere(sl.data>np.percentile(sl.data,95)).flatten() # brightest points
            xcentroid,ycentroid  = np.nanmean(x[argmaxes]),np.nanmean(y[argmaxes]) # centroid
            if not centroid_err_given:
                centroids_err = [5,5]
                            
                position_type="auto" 
        else:
            print("IFU position based on CCD wcs solution used : ",xcentroid,ycentroid)
            position_type="astrom" 
    else:
        xcentroid, ycentroid = np.asarray(centroid, dtype="float")
        print("centroid used", centroid)
        position_type="manual"

    return [xcentroid, ycentroid], centroids_err, position_type


#################################
#
#   MAIN 
#
#################################
if  __name__ == "__main__":
    
    import argparse
    import numpy as np
    from shapely      import geometry
    # 
    from psfcube      import script
    from pysedm       import get_sedmcube, io, fluxcalibration, sedm
    from pysedm.sedm  import IFU_SCALE_UNIT
    
    # ================= #
    #   Options         #
    # ================= #
    parser = argparse.ArgumentParser(
        description=""" run the interactive plotting of a given cube
            """, formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('infile', type=str, default=None,
                        help='cube filepath')

    # // AUTOMATIC EXTRACTION

    #  which extraction
    # Auto PSF
    parser.add_argument('--auto',  type=str, default=None,
                        help='Shall this run an automatic PSF extraction')

    parser.add_argument('--autorange',  type=str, default="4500,7000",
                        help='Wavelength range [in Angstrom] for measuring the metaslice PSF')
    
    parser.add_argument('--autobins',  type=int, default=7,
                        help='Number of bins within the wavelength range (see --autorange)')

    parser.add_argument('--buffer',  type=float, default=8,
                        help='Radius [in spaxels] of the aperture used for the PSF fit. (see --centroid for aperture center)')

    parser.add_argument('--psfmodel',  type=str, default="NormalMoffatTilted",
                        help='PSF model used for the PSF fit: NormalMoffat{Flat/Tilted/Curved}')

    # Apperture


    # // Generic information
    parser.add_argument('--centroid',  type=str, default="None",nargs=2,
                        help='Where is the point source expected to be? using the "x,y" format. If None, it will be guessed.'+
                            "\nGuess works well for isolated sources.")
    
    parser.add_argument('--centroiderr',  type=str, default="None",nargs=2,
                        help='What error do you expect on your given centroid.'+
                            '\nIf not provided, it will be 3 3 for general cases and 5 5 for maximum brightnes backup plan')
    
    parser.add_argument('--lstep',  type=int, default=1,
                        help='Slice width in lbda step: default is 1, use 2 for fainter source and maybe 3 for really faint target')
    
    parser.add_argument('--display',  action="store_true", default=False,
                        help='Select the area to fit using the display function.')
    

    # - Standard Star object
    parser.add_argument('--std',  action="store_true", default=False,
                        help='Set this to True to tell the program you what to build a calibration spectrum from this object')
    
    parser.add_argument('--fluxcalsource',  type=str, default="None",
                        help='Path to a "fluxcal" .fits file. This file will be used for the flux calibration. If nothing given, the nearest (in time and within the night) fluxcal will be used.')
    

    parser.add_argument('--nofluxcal',  action="store_true", default=False,
                        help='No Flux calibration')
    
    parser.add_argument('--nofig',    action="store_true", default=False,
                        help='')

        
    args = parser.parse_args()
        
    # ================= #
    #   The Scripts     #
    # ================= #

    # --------- #
    #  Date     #
    # --------- #
    date = args.infile

    
    # ================= #
    #   Actions         #
    # ================= #
    extracted_objects = []
    # ---------- #
    # Extraction #
    # ---------- #


    
    # - Automatic extraction
    if args.auto is not None and len(args.auto) >0:
        final_slice_width = int(args.lstep)
        # - Step 1 parameters
        lbdaranges, bins = np.asarray(args.autorange.split(","), dtype="float"), int(args.autobins+1)
        STEP_LBDA_RANGE = np.linspace(lbdaranges[0],lbdaranges[1], bins+1)
        lbda_step1      = np.asarray([STEP_LBDA_RANGE[:-1], STEP_LBDA_RANGE[1:]]).T
        
        for target in args.auto.split(","):
            filecubes = io.get_night_files(date, "cube.*", target=target.replace(".fits",""))
            print("cube file from which the spectra will be extracted: "+ ", ".join(filecubes))
            
            # - loop over the file cube
            for filecube in filecubes:
                # ----------------- #
                #  Cube to Fit?     #
                # ----------------- #
                print("Automatic extraction of target %s, file: %s"%(target, filecube))
                cube_ = get_sedmcube(filecube)
                [xcentroid, ycentroid], centroids_err, position_type = position_source(cube_, centroid = args.centroid, centroiderr= args.centroiderr)
                if args.display:
                    iplot = cube_.show(interactive=True, launch=False)
                    iplot.axim.scatter( xcentroid, ycentroid, **MARKER_PROP[position_type] )
                    iplot.launch(vmin="2", vmax="98", notebook=False)
                    cube = cube_.get_partial_cube( iplot.get_selected_idx(), np.arange( len(cube_.lbda)) )
                    args.buffer = 20
                    if iplot.picked_position is not None:
                        print("You picked the position : ", iplot.picked_position )
                        print(" updating the centroid accordingly ")
                        xcentroid, ycentroid = iplot.picked_position
                        centroids_err = [1.5,1.5]
                        position_type = "manual"
                else:
                    cube = cube_
                    
                # Centroid ?    
                print("INFO: PSF centroid (%s)**"%position_type)
                print("centroid: %.1f %.1f"%(xcentroid, ycentroid)+ " error: %.1f %.1f"%(centroids_err[0], centroids_err[1]))
                
                # Aperture area ?
                point_polygon = geometry.Point(xcentroid, ycentroid).buffer( float(args.buffer) )
                # => Cube to fit
                cube_to_fit = cube.get_partial_cube( cube.get_spaxels_within_polygon(point_polygon),
                                                      np.arange(len(cube.lbda)))
                # --------------
                # Fitting
                # --------------
                print("INFO: Starting MetaSlice fit")
                spec, cubemodel, psfmodel, bkgdmodel, psffit, slpsf  = \
                  script.extract_star(cube_to_fit,
                                          centroids=[xcentroid, ycentroid], centroids_err=centroids_err,
                                          spaxel_unit = IFU_SCALE_UNIT,
                                          final_slice_width = final_slice_width,
                                          lbda_step1=lbda_step1, psfmodel=args.psfmodel)
                # Hack to be removed:
                print("INFO: Temporary variance hacking to be removed ")
                spec._properties['variance'] = np.ones(len(spec.lbda)) * np.median(spec.variance)

                if final_slice_width != 1:
                    spec = spec.reshape(cube.lbda)

                spec_raw = spec.copy()
                # --------------
                # Flux Calibation
                # --------------
                notflux_cal=False
                if not args.nofluxcal:
                    # Which Flux calibration file ?
                    if args.fluxcalsource is None or args.fluxcalsource in ["None"]:
                        print("INFO: default nearest fluxcal file used")
                        fluxcalfile = io.fetch_nearest_fluxcal(date, cube.filename)
                    else:
                        print("INFO: given fluxcal used.")
                        fluxcalfile =  args.fluxcalsource 

                    # Do I have a flux calibration file ?
                    if fluxcalfile is None:
                        print("ERROR: No fluxcal for night %s and no alternative fluxcalsource provided. Uncalibrated spectra saved."%date)
                        spec.header["FLUXCAL"] = ("False","has the spectra been flux calibrated")
                        spec.header["CALSRC"] = (None, "Flux calibrator filename")
                        notflux_cal=True
                    else:
                        from pyifu import load_spectrum
                        fluxcal = load_spectrum( fluxcalfile ) 
                        spec.scale_by(1/fluxcal.data)
                        spec.header["FLUXCAL"] = ("True","has the spectra been flux calibrated")
                        spec.header["CALSRC"] = (fluxcal.filename.split("/")[-1], "Flux calibrator filename")
                        notflux_cal=False
                        
                else:
                    spec.header["FLUXCAL"] = ("False","has the spectra been flux calibrated")
                    spec.header["CALSRC"] = (None, "Flux calibrator filename")
                    notflux_cal=True
                # --------------
                # header info passed
                # --------------
                for k,v in cube.header.items():
                    if k not in spec.header:
                        spec.header.set(k,v)
                        spec_raw.header.set(k,v)
                        
                # --------------
                # Recording
                # --------------
                add_info_spec = "_notfluxcal" if notflux_cal else ""
                spec_info = "_lstep%s"%final_slice_width + add_info_spec
                io._saveout_forcepsf_(filecube, cube, cuberes=None, cubemodel=cubemodel,
                                          mode="auto",spec_info=spec_info,
                                          cubefitted=cube_to_fit, spec=spec)
                # Figure
                if not args.nofig:
                    psffit.show_adr(savefile=spec.filename.replace("spec","adr_fit").replace(".fits",".pdf") ) 
                    psffit.slices[2]["slpsf"].show(savefile=spec.filename.replace("spec","psfprofile").replace(".fits",".pdf"))
                    psffit.slices[2]["slpsf"].show(savefile=spec.filename.replace("spec","psfprofile").replace(".fits",".png"))
                    
                    import matplotlib.pyplot as mpl
                    cube_.show(show=False)
                    ax = mpl.gca()
                    x,y = np.asarray(cube_to_fit.index_to_xy(cube_to_fit.indexes)).T
                    ax.plot(x,y, marker=".", ls="None", ms=1, color="k")
                    ax.scatter(xcentroid, ycentroid, **MARKER_PROP[position_type])
                    ax.figure.savefig(spec.filename.replace("spec","spaxels_source").replace(".fits",".pdf"))
                    
                    # Pure spaxel
                    fig = mpl.figure(figsize=[3.5,3.5])
                    ax  = ax = fig.add_axes([0.15,0.15,0.75,0.75])
                    _ = cube_._display_im_(ax, vmax="98", vmin="2")
                    ax.plot(x,y, marker=".", ls="None", ms=1, color="k")
                    ax.scatter(xcentroid, ycentroid, **MARKER_PROP[position_type])
                    ax.figure.savefig(spec.filename.replace("spec","ifu_spaxels_source").replace(".fits",".pdf"))
                    ax.figure.savefig(spec.filename.replace("spec","ifu_spaxels_source").replace(".fits",".png"), dpi=150)
                    
                    # Special Standard
                    if cube.header['IMGTYPE'].lower() in ['standard'] and not notflux_cal:
                        from pysedm.fluxcalibration import show_fluxcalibrated_standard
                        show_fluxcalibrated_standard(spec, savefile=spec.filename.replace("spec","calibcheck_spec").replace(".fits",".pdf"))
                        show_fluxcalibrated_standard(spec, savefile=spec.filename.replace("spec","calibcheck_spec").replace(".fits",".png"))
                        
                # -----------------
                #  Is that a STD  ?
                # -----------------
                if args.std and cube.header['IMGTYPE'].lower() in ['standard']:
                    # Based on the flux non calibrated spectra
                    spec_raw.header['OBJECT'] = cube.header['OBJECT']
                    speccal, fl = fluxcalibration.get_fluxcalibrator(spec_raw, fullout=True)
                    for k,v in cube.header.items():
                        if k not in speccal.header:
                            speccal.header.set(k,v)

                    speccal.header["SOURCE"] = (spec.filename.split("/")[-1], "This object has been derived from this file")
                    speccal.header["PYSEDMT"] = ("Flux Calibration Spectrum", "Object to use to flux calibrate")
                    filename_inv = spec.filename.replace(io.PROD_SPECROOT,io.PROD_SENSITIVITYROOT)
                    speccal._side_properties['filename'] = filename_inv
                    speccal.writeto(filename_inv)
                    if not args.nofig:
                        fl.show(savefile=speccal.filename.replace(".fits",".pdf"), show=False, fluxcal=speccal.data)
                        fl.show(savefile=speccal.filename.replace(".fits",".png"), show=False, fluxcal=speccal.data)
                                    
                # - for the record
                extracted_objects.append(spec)
                
    else:
        print("NO  AUTO")
        
