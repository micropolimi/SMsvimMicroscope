from threading import Thread
import numpy as np
import time
from smTriggered_Measurement import StructuredLightTriggeredMeasurement
from PI_ScopeFoundry.PIPython.pipython import GCSDevice, pitools
from ScopeFoundry.helper_funcs import sibling_path, load_qt_ui_file
from ScopeFoundry import h5_io
import pyqtgraph as pg
import os
import math
from qtpy import QtCore, QtWidgets

CONTROLLERNAME = 'C-413'
STAGES = ['V-524.1AA']  # connect stages to axes
REFMODES = ['FRF']  # reference the connected stages

NUMCYLES = 10  # number of cycles for wave generator output
TABLERATE = 2  # duration of a wave table point in multiples of servo cycle times as integer
AXIS = ['1']
WAVE_GENERATOR_IDS = [1]
WAVE_TABLE_IDS = [1]
TIMEOUT = 300

class SMsvimMeasurement(StructuredLightTriggeredMeasurement):

    name = "SMsvimMeasurement"

    def setup(self):

        self.previous_settings = {}
        self.ui_filename = sibling_path(__file__, "smSVIM.ui")
        
        self.ui = load_qt_ui_file(self.ui_filename)
        self.settings.New('refresh_period', dtype=float, unit='s', spinbox_decimals = 4, initial=0.02 , hardware_set_func=self.setRefresh, vmin = 0)
        self.settings.New('autoRange', dtype=bool, initial=True, hardware_set_func=self.setautoRange)
        self.settings.New('autoLevels', dtype=bool, initial=True, hardware_set_func=self.setautoLevels)
        self.settings.New('level_min', dtype=int, initial=0, hardware_set_func=self.setminLevel, hardware_read_func = self.getminLevel)
        self.settings.New('level_max', dtype=int, initial=2**16, vmax = 2**16,  hardware_set_func=self.setmaxLevel, hardware_read_func = self.getmaxLevel)
        self.settings.New("rotate_image", dtype=str, choices=["0", "90", "180", "270"], initial="270", ro=True)
        self.settings.New("waveform_number_of_points", dtype=int, initial = 0, vmin = 0, ro=True)
        """
        To have the best coherence between different functions, I have created two directories settings.
        In fact many operations require an input folder (from which fetching data) and an output folder
        (in which saving data). Therefore one must decide from which directory fetching data and where saving data.
        """
        
        self.settings.New("input_directory", dtype = 'file', is_dir = True, 
                                               initial = "D:/LabPrograms/Python/DMD_Pattern/encd_Patterns/multiple_Pattern_Encoding_SVIMMeasurement/encd_bin_Alternated_Hadamard_128Pixel/")
        self.settings.New("output_directory", dtype = 'file', is_dir = True, 
                                               initial = "D:/LabPrograms/Python/DMD_Pattern/bin_Patterns/")
        self.settings.New("waveform_directory", dtype = 'file', is_dir = True, 
                                               initial = "D:/LabPrograms/Python/PI_stage/waveform/")

                
        self.add_operation("input_browser", self.input_file_browser)
        self.add_operation("output_browser", self.output_file_browser)
        self.add_operation("waveform_browser", self.waveform_file_browser)
                
        self.camera = self.app.hardware['HamamatsuHardware']
        self.dmd_hw = self.app.hardware["DmdHardware"]
        
        self.autoRange = self.settings.autoRange.val
        self.display_update_period = self.settings.refresh_period.val
        self.autoLevels = self.settings.autoLevels.val
        self.level_min = self.settings.level_min.val
        self.level_max = self.settings.level_max.val
        self.pi_hw = self.app.hardware["PIStageNew"]

    @QtCore.Slot()    
    def waveform_file_browser(self):
        """
        Opens a dialog when click on browser, and update the value of the output_directory
        for saving data.
        """

        if self.settings.output_directory.is_dir:
            fname = QtWidgets.QFileDialog.getExistingDirectory(directory = self.settings.waveform_directory.val[:-1])
        else:
            fname, _ = QtWidgets.QFileDialog.getOpenFileName(directory = self.settings.waveform_directory.val[:-1])
            
        self.settings.waveform_directory.log.debug(repr(fname))
        self.settings.waveform_directory.update_value(fname + "/")
        
    def setup_figure(self):
        
        """
        Runs once during App initialization, after setup()
        This is the place to make all graphical interface initializations,
        build plots, etc.
        """
                
        # connect ui widgets to measurement/hardware settings or functions
        self.ui.start_pushButton.clicked.connect(self.start)
        self.ui.interrupt_pushButton.clicked.connect(self.interrupt)
        
        # connect ui widgets of live settings
        self.settings.autoLevels.connect_to_widget(self.ui.autoLevels_checkBox)
        self.settings.autoRange.connect_to_widget(self.ui.autoRange_checkBox)
        self.settings.level_min.connect_to_widget(self.ui.min_doubleSpinBox) #spinBox doesn't work nut it would be better
        self.settings.level_max.connect_to_widget(self.ui.max_doubleSpinBox) #spinBox doesn't work nut it would be better
        
        self.camera.settings.connected.connect_to_widget(self.ui.connected_checkBox)
        
        """
        NOTICE
        
        For some reason, the trigger_source setting does not change value when the widget change (and vice-versa).
        In other words, they are not synchronized (I think is due to the reread_from_hardware_after_write of the setting).
        Anyway, the value that the software consider is the one of the widget/setting that changed last.
        """
        self.camera.settings.exposure_time.connect_to_widget(self.ui.exposure_time_doubleSpinBox)
        
        self.dmd_hw.settings.connected.connect_to_widget(self.ui.connected_checkBox_2)
        self.dmd_hw.settings.exposure.connect_to_widget(self.ui.exposure_doubleSpinBox)
        
        self.pi_hw.settings.connected.connect_to_widget(self.ui.pi_connected_checkBox)
                
        self.settings.input_directory.connect_to_widget(self.ui.input_directory_lineEdit)
        self.settings.waveform_directory.connect_to_widget(self.ui.waveform_directory_lineEdit)
        self.ui.waveform_search_pushButton.clicked.connect(self.waveform_file_browser)
        self.settings.progress.connect_to_widget(self.ui.progress_progressBar)
        self.ui.search_pushButton.clicked.connect(self.input_file_browser)
        # Set up pyqtgraph graph_layout in the UI
        self.imv = pg.ImageView()
        self.ui.plot_groupBox.layout().addWidget(self.imv)
        
        # Image initialization
        self.image = np.zeros((int(self.camera.subarrayv.val),int(self.camera.subarrayh.val)),dtype=np.uint16)

        self.image = np.zeros((int(self.camera.subarrayv.val),int(self.camera.subarrayh.val)),dtype=np.uint16)
        self.pi_hw.pp_amplitude.connect_to_widget(self.ui.pp_amplitude_doubleSpinBox)  
        self.pi_hw.settings.x_target.connect_to_widget(self.ui.starting_position_doubleSpinBox)     
        

        self.camera.internal_line_interval.connect_to_widget(self.ui.internal_line_interval_doubleSpinBox)
        self.camera.frame_exposure_time.connect_to_widget(self.ui.frame_exposure_time_doubleSpinBox)
        self.camera.sensor_mode.connect_to_widget(self.ui.sensor_mode_comboBox)
                
        self.settings.rotate_image.connect_to_widget(self.ui.rotate_image_comboBox)  
        self.settings.waveform_number_of_points.connect_to_widget(self.ui.waveform_number_of_points_doubleSpinBox) 
        
        self.ui.try_movement_pushButton.clicked.connect(self.threadedTryMovement)
        self.ui.set_home_pushButton.clicked.connect(self.pi_hw.set_home)
        self.ui.save_txt_waveform_pushButton.clicked.connect(self.generateWaveform)
        
        self.image = np.zeros((int(self.camera.subarrayv.val),int(self.camera.subarrayh.val)),dtype=np.uint16)
        self.image[0,0] = 1 
        
    
    def generateWaveform(self):
        """
        Python module to generate a txt file for the PI movement
        """
        #Duration of a table's point
        pi_point_time = 202.666*10**-6 
        
        #Total exposure of the frame (WARNING! MAYBE IS NOT SUBARRAYH BUT SUBARRAYV!!!)
        camera_exposure = self.camera.exposure_time.val + self.camera.subarrayv.val*self.camera.internal_line_interval.val
        
        print("The exposure of a frame lasts for :", camera_exposure)
        #Dmd exposure time (the logged quantity is in us, therefore the term 10**-6)
        dmd_exposure = self.dmd_hw.exposure.val*10**-6
        
        #Dmd exposure time (the logged quantity is in us, therefore the term 10**-6)
        rising_time = camera_exposure #to moduify
        falling_time = dmd_exposure - rising_time
        
        #If the condition is not True, it stops and gives an error
        assert rising_time + falling_time <= dmd_exposure
        
        #Number of points for the rising and falling edge of the waveform
        float_rising_points = rising_time/pi_point_time
        float_falling_points = falling_time/pi_point_time
        
        float_rising_points /= TABLERATE
        float_falling_points /= TABLERATE
        
        rising_points = int(float_rising_points)
        falling_points = int(float_falling_points)
        
        error = float_rising_points + float_falling_points - rising_points - falling_points 
        
        self.single_frame_time_error = error*pi_point_time
        
        self.dmd_hw.exposure.update_value(new_val = int((rising_points+falling_points)*pi_point_time*TABLERATE*10**6))
        
        self.final_position = self.pi_hw.home + self.pi_hw.pp_amplitude.val
        
        y_rising = np.linspace(self.pi_hw.home, self.final_position, rising_points)
        y_falling = np.linspace(self.final_position, self.pi_hw.home, falling_points)
                
        y_waveform = np.concatenate((y_rising, y_falling))
        """
        The following commented lines needs to be used when a second axis is added, therefore delete the last np.savetext and use the commented lines
        """
        #y_second_axis = np.zeros(len(y_waveform)) #this column is necessary to pass the table to the PI, even if it is not used
        
        #y_table = np.array([y_waveform, y_second_axis])
        
        #np.savetxt("C:\\Users\\OPT\\Desktop\\waveform.txt", np.transpose(y_table), fmt = "%.3f")
        
        if os.path.exists(self.settings.waveform_directory.val + "waveform.txt"):
            os.remove(self.settings.waveform_directory.val + "waveform.txt")
        
        np.savetxt(self.settings.waveform_directory.val + "waveform.txt", y_waveform, fmt = "%.3f")
        
        self.settings.waveform_number_of_points.update_value(new_val = len(y_waveform))

        
    def threadedTryMovement(self):
        
        t1 = Thread(target=self.tryMovement)
        t1.start()
    
    def tryMovement(self):
        """Read wave data, set up wave generator and run them.
        @type pidevice : pipython.gcscommands.GCSCommands
        """
        
        wavedata = self.readwavedata()
        axes = self.pi_hw.pidevice.axes[:len(wavedata)]
        assert len(wavedata) == len(axes), 'this sample requires {} connected axes'.format(len(wavedata))
        if self.pi_hw.pidevice.HasWCL():  # you can remove this code block if your controller does not support WCL()
            print('clear wave tables {}'.format(WAVE_TABLE_IDS))
            self.pi_hw.pidevice.WCL(WAVE_TABLE_IDS)
        for wavetable in WAVE_TABLE_IDS:
            for point in wavedata[wavetable-1]:
                self.pi_hw.pidevice.WAV_PNT(table=wavetable, firstpoint=1, numpoints=1, append='&', wavepoint=point)
        if self.pi_hw.pidevice.HasWSL():  # you can remove this code block if your controller does not support WSL()
            print('connect wave tables {} to wave generators {}'.format(WAVE_TABLE_IDS, WAVE_GENERATOR_IDS))
            self.pi_hw.pidevice.WSL(WAVE_GENERATOR_IDS, WAVE_TABLE_IDS)
        if self.pi_hw.pidevice.HasWGC():  # you can remove this code block if your controller does not support WGC()
            print('set wave generators {} to run for {} cycles'.format(WAVE_GENERATOR_IDS, NUMCYLES))
            print(NUMCYLES)
            self.pi_hw.pidevice.WGC(WAVE_GENERATOR_IDS, NUMCYLES * len(WAVE_GENERATOR_IDS))
        if self.pi_hw.pidevice.HasWTR():  # you can remove this code block if your controller does not support WTR()
            print('set wave table rate to {} for wave generators {}'.format(TABLERATE, WAVE_GENERATOR_IDS))
            self.pi_hw.pidevice.WTR(WAVE_GENERATOR_IDS, TABLERATE * len(WAVE_GENERATOR_IDS), 0 * len(WAVE_GENERATOR_IDS))
        start_position = [wavedata[i][0] for i in range(len(AXIS))]
        print('move axes {} to start positions {}'.format(axes, start_position))
        self.pi_hw.pidevice.MOV(AXIS, start_position)
        maxtime = time.time() + TIMEOUT
        while not all(list(self.pi_hw.pidevice.qONT(AXIS).values())):
            if time.time() > maxtime:
                raise SystemError('waitontarget() timed out after %.1f seconds' % TIMEOUT)
            time.sleep(0.1)
    
        print('start wave generators {}'.format(WAVE_GENERATOR_IDS))
        self.pi_hw.pidevice.WGO(1, mode=1)
        while any(list(self.pi_hw.pidevice.IsGeneratorRunning([1]).values())):
            print('.', end='')
            time.sleep(1.0)
        print('\nreset wave generators {}'.format(WAVE_GENERATOR_IDS))
        self.pi_hw.pidevice.WGO(1, mode=0)
        print('done')
    

    def init_periodic_motion(self):
        
        """Read wave data, set up wave generator and run them.
        @type pidevice : pipython.gcscommands.GCSCommands
        """
        
        wavedata = self.readwavedata()
        axes = self.pi_hw.pidevice.axes[:len(wavedata)]
        assert len(wavedata) == len(axes), 'this sample requires {} connected axes'.format(len(wavedata))
        if self.pi_hw.pidevice.HasWCL():  # you can remove this code block if your controller does not support WCL()
            print('clear wave tables {}'.format(WAVE_TABLE_IDS))
            self.pi_hw.pidevice.WCL(WAVE_TABLE_IDS)
        for wavetable in WAVE_TABLE_IDS:
            for point in wavedata[wavetable-1]:
                self.pi_hw.pidevice.WAV_PNT(table=wavetable, firstpoint=1, numpoints=1, append='&', wavepoint=point)
        if self.pi_hw.pidevice.HasWSL():  # you can remove this code block if your controller does not support WSL()
            print('connect wave tables {} to wave generators {}'.format(WAVE_TABLE_IDS, WAVE_GENERATOR_IDS))
            self.pi_hw.pidevice.WSL(WAVE_GENERATOR_IDS, WAVE_TABLE_IDS)
        if self.pi_hw.pidevice.HasWGC():  # you can remove this code block if your controller does not support WGC()
            print('set wave generators {} to run for {} cycles'.format(WAVE_GENERATOR_IDS, self.camera.hamamatsu.number_frames))
            self.pi_hw.pidevice.WGC(WAVE_GENERATOR_IDS, self.camera.hamamatsu.number_frames * len(WAVE_GENERATOR_IDS))
        if self.pi_hw.pidevice.HasWTR():  # you can remove this code block if your controller does not support WTR()
            print('set wave table rate to {} for wave generators {}'.format(TABLERATE, WAVE_GENERATOR_IDS))
            self.pi_hw.pidevice.WTR(WAVE_GENERATOR_IDS, TABLERATE * len(WAVE_GENERATOR_IDS), 0 * len(WAVE_GENERATOR_IDS))
        start_position = [wavedata[i][0] for i in range(len(AXIS))]
        print('move axes {} to start positions {}'.format(axes, start_position))
        self.pi_hw.pidevice.MOV(AXIS, start_position)
        
        
        print("The time needed ")
        maxtime = time.time() + TIMEOUT
        while not all(list(self.pi_hw.pidevice.qONT(AXIS).values())):
            if time.time() > maxtime:
                raise SystemError('waitontarget() timed out after %.1f seconds' % TIMEOUT)
            time.sleep(0.1)
        
        self.total_time_error = self.single_frame_time_error*self.camera.hamamatsu.number_frames
        
        print("The predicted lag between pi and camera-dmd is: ", self.total_time_error)
        
    def periodic_motion(self):
        
        print('start wave generators {}'.format(WAVE_GENERATOR_IDS))
        self.pi_hw.pidevice.WGO(1, mode=1)
    

    def readwavedata(self):
        """Read DATAFILE, must have a column for each wavetable.
        @return : Datapoints as list of lists of values.
        """
        self.DATAFILE = self.settings.waveform_directory.val + "waveform.txt"
        
        print('read wave points from file {}'.format(self.DATAFILE))
        data = None
        with open(self.DATAFILE) as datafile:
            for line in datafile:
                items = line.strip().split()
                if data is None:
                    print('found {} data columns in file'.format(len(items)))
                    data = [[] for _ in range(len(items))]
                for i, item in enumerate(items):
                    data[i].append(item)
        return data
                 
    def run(self):
        
        self.time_0 = None
        self.eff_subarrayh = int(self.camera.subarrayh.val/self.camera.binning.val)
        self.eff_subarrayv = int(self.camera.subarrayv.val/self.camera.binning.val)
        
        self.image = np.zeros((self.eff_subarrayv,self.eff_subarrayh),dtype=np.uint16)
        
        self.image[0,0] = 1 #Otherwise we get the "all zero pixels" error (we should modify pyqtgraph...)
        self.image[self.eff_subarrayv-1,0] = 1
        self.image[0,self.eff_subarrayh-1] = 1
        self.image[self.eff_subarrayv-1,self.eff_subarrayh-1] = 1
        
        try:
            self.camera.trsource.update_value(new_val = 'external')
            
            if self.pi_hw.pp_amplitude.val > 0:
                self.camera.readout_direction.update_value(new_val = 'forward')
            
            elif self.pi_hw.pp_amplitude.val < 0:
                self.camera.readout_direction.update_value(new_val = 'backward')
            
            else:
                print("The amplitude of the PI cannot be zero, choose a new value.")
                finished = True
                
            exposure=[self.dmd_hw.exposure.val]
            dark_time=[self.dmd_hw.dark_time.val]
            trigger_input=[self.dmd_hw.trigger_input.val]
            trigger_output=[True]

            index = 0
            
            patterns = []
            patterns, extension = self.taking_patterns()
                
            index = 0 #I don't think it's necessary
            first = 0
            finished = False

            while not finished:

                if first == 0:
                    
                    self.number_patterns = self.dmd_hw.dmd.def_sequence_by_file(self.settings.input_directory.val + patterns[0], exposure, trigger_input, dark_time, trigger_output, 0)
                    self.camera.hamamatsu.number_frames = self.number_patterns
                    self.camera.number_frames.val = self.number_patterns
                    self.camera.hamamatsu.startAcquisition()
                    self.init_periodic_motion()
                    t1 = Thread(target=self.periodic_motion)
                    t1.start()
                    self.dmd_hw.dmd.startsequence()
                    
                    self.time_0 = time.time()
                    
                    self.initH5()
                    print("\n \n ******* \n \n Saving :D !\n \n *******")
                    first = 1

                    # Get frames.
                    #The camera stops acquiring once the buffer is terminated (in snapshot mode)
                [frames, dims] = self.camera.hamamatsu.getFrames()

                # Save frames.
                for aframe in frames:

                    self.np_data = aframe.getData()
                    self.image = np.reshape(self.np_data,(self.eff_subarrayv, self.eff_subarrayh))
                    self.image_h5[index,:,:] = self.image # saving to the h5 dataset
                    self.h5file.flush() # maybe is not necessary

                    if self.interrupt_measurement_called:
                        break
                    index+=1
                    print(index)

                if self.interrupt_measurement_called:
                    break
                #index = index + len(frames)
                #np_data.tofile(bin_fp)
                self.settings['progress'] = index*100./self.number_patterns

                if index >= self.number_patterns:
                    finished = True
            
        finally:

            self.camera.hamamatsu.stopAcquisition()
            self.dmd_hw.dmd.stopsequence()
            self.pi_hw.stop()
            
            if self.h5file:
                self.h5file.close()
            
    def update_display(self):
        """
        Displays the numpy array called self.image.  
        This function runs repeatedly and automatically during the measurement run,
        its update frequency is defined by self.display_update_period.
        """
        if self.settings.rotate_image.val == "0":
            self.visualized_image = self.image
        
        elif self.settings.rotate_image.val == "90":
            self.visualized_image = np.rot90(self.image)
        
        elif self.settings.rotate_image.val == "180":
            self.visualized_image = np.rot90(self.image, 2)
        
        else:
            self.visualized_image = np.rot90(self.image, 3)

        if self.autoLevels == False:  
            self.imv.setImage((self.visualized_image).T, autoLevels=self.settings.autoLevels.val, autoRange=self.settings.autoRange.val, levels=(self.settings.level_min.val, self.settings.level_max.val))
        else: #levels should not be sent when autoLevels is True, otherwise the image is displayed with them
            self.imv.setImage((self.visualized_image).T, autoLevels=self.settings.autoLevels.val, autoRange=self.settings.autoRange.val)
            self.settings.level_min.read_from_hardware()
            self.settings.level_max.read_from_hardware()
        
        if self.time_0 is not None:
            self.time_1 = time.time()
            self.time_passed = self.time_1 - self.time_0
            self.minutes = math.floor(self.time_passed/60)
            self.seconds = self.time_passed%60
            self.ui.minutes_lcdNumber.display(self.minutes)
            self.ui.seconds_lcdNumber.display(self.seconds)
