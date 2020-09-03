from threading import Thread
import numpy as np
import time
from smTriggered_Measurement import StructuredLightTriggeredMeasurement
from PI_ScopeFoundry.PIPython.pipython import pitools
from ScopeFoundry.helper_funcs import sibling_path, load_qt_ui_file
import pyqtgraph as pg

class CalibrationMeasurement(StructuredLightTriggeredMeasurement):
    
    name = "CalibrationMeasurement"

    def setup(self):

        self.previous_settings = {}
        self.ui_filename = sibling_path(__file__, "calibration.ui")
        
        self.ui = load_qt_ui_file(self.ui_filename)
        
        self.settings.New('refresh_period', dtype=float, unit='s', spinbox_decimals = 4, initial=0.02, vmin = 0)
        self.settings.refresh_period.hardware_set_func = self.setRefresh
        
        self.settings.New('autoRange', dtype=bool, initial=True)
        self.settings.autoRange.hardware_set_func = self.setautoRange
        
        self.settings.New('autoLevels', dtype=bool, initial=True)
        self.settings.autoLevels.hardware_set_func = self.setautoLevels        
        
        self.settings.New('level_min', dtype=int, initial=0)
        self.settings.level_min.hardware_set_func = self.setminLevel          
        self.settings.level_min.hardware_read_func = self.getminLevel    
                
        self.settings.New('level_max', dtype=int, initial=2**16, vmax = 2**16)
        self.settings.level_max.hardware_set_func = self.setmaxLevel         
        self.settings.level_max.hardware_read_func = self.getmaxLevel 
        
        self.settings.New("rotate_image", dtype=str, choices=["0", "90", "180", "270"], initial="270", ro=True)
        
        """
        To have the best coherence between different functions, I have created two directories settings.
        In fact many operations require an input folder (from which fetching data) and an output folder
        (in which saving data). Therefore one must decide from which directory fetching data and where saving data.
        """
        self.camera = self.app.hardware['HamamatsuHardware']
        self.pi_hw = self.app.hardware["PIStageNew"]
        
        self.autoRange = self.settings.autoRange.val
        self.display_update_period = self.settings.refresh_period.val
        self.autoLevels = self.settings.autoLevels.val
        self.level_min = self.settings.level_min.val
        self.level_max = self.settings.level_max.val

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
        self.pi_hw.settings.connected.connect_to_widget(self.ui.connected_pi_checkBox)
        """
        NOTICE
        
        For some reason, the trigger_source setting does not change value when the widget change (and vice-versa).
        In other words, they are not synchronized (I think is due to the reread_from_hardware_after_write of the setting).
        Anyway, the value that the software consider is the one of the widget/setting that changed last.
        """
        self.camera.settings.internal_frame_rate.connect_to_widget(self.ui.internal_frame_rate_doubleSpinBox)
        self.camera.settings.exposure_time.connect_to_widget(self.ui.exposure_time_doubleSpinBox)
        
        self.settings.progress.connect_to_widget(self.ui.progress_progressBar)
        # Set up pyqtgraph graph_layout in the UI
        self.imv = pg.ImageView()
        self.ui.plot_groupBox.layout().addWidget(self.imv)
        
        # Image initialization
#        self.image = np.zeros((int(self.camera.subarrayv.val)+2,int(self.camera.subarrayh.val))+2,dtype=np.uint16)
        self.image = np.zeros((int(self.camera.subarrayv.val),int(self.camera.subarrayh.val)),dtype=np.uint16)
        
        """adding white frame to image to be displayed"""
        
#         self.image[0,:] = 2**16
#         self.image[1,:] = 2**16
#         self.image[:,0] = 2**16
#         self.image[:,1] = 2**16
#         
#         self.image[int(self.camera.subarrayv.val)+1,:] = 2**16
#         self.image[int(self.camera.subarrayv.val),:] = 2**16
#         self.image[:,int(self.camera.subarrayv.val)+1] = 2**16
#         self.image[:,int(self.camera.subarrayv.val)] = 2**16
        
        self.pi_hw.pp_amplitude.connect_to_widget(self.ui.pp_amplitude_doubleSpinBox)
        self.pi_hw.settings.x_target.connect_to_widget(self.ui.starting_position_doubleSpinBox)     
        
        self.camera.internal_line_interval.connect_to_widget(self.ui.internal_line_interval_doubleSpinBox)
        self.camera.internal_frame_interval.connect_to_widget(self.ui.internal_frame_interval_doubleSpinBox)
        self.camera.readout_direction.connect_to_widget(self.ui.readout_direction_comboBox)
        self.camera.sensor_mode.connect_to_widget(self.ui.sensor_mode_comboBox)
        
        self.settings.rotate_image.connect_to_widget(self.ui.rotate_image_comboBox)  
        

        self.ui.set_home_pushButton.clicked.connect(self.pi_hw.set_home)
        
        self.visualized_image = self.image

#         self.visualized_image[0,:] = 2**16
#         self.visualized_image[1,:] = 2**16
#         self.visualized_image[:,0] = 2**16
#         self.visualized_image[:,1] = 2**16
#         
#         self.visualized_image[int(self.camera.subarrayv.val)+1,:] = 2**16
#         self.visualized_image[int(self.camera.subarrayv.val),:] = 2**16
#         self.visualized_image[:,int(self.camera.subarrayv.val)+1] = 2**16
#         self.visualized_image[:,int(self.camera.subarrayv.val)] = 2**16

    def run(self):

        self.eff_subarrayh = int(self.camera.subarrayh.val/self.camera.binning.val)
        self.eff_subarrayv = int(self.camera.subarrayv.val/self.camera.binning.val)
        
        self.image = np.zeros((self.eff_subarrayv,self.eff_subarrayh),dtype=np.uint16)
        
        self.image[0,0] = 1 #Otherwise we get the "all zero pixels" error (we should modify pyqtgraph...)
        self.image[self.eff_subarrayv-1,0] = 1
        self.image[0,self.eff_subarrayh-1] = 1
        self.image[self.eff_subarrayv-1,self.eff_subarrayh-1] = 1
        
        self.visualized_image = np.zeros((self.eff_subarrayv,self.eff_subarrayh),dtype=np.uint16)
        self.visualized_image[0,0] = 1 #Otherwise we get the "all zero pixels" error (we should modify pyqtgraph...)

#         self.visualized_image = np.zeros((self.eff_subarrayv+4,self.eff_subarrayh+4),dtype=np.uint16)
#         self.visualized_image[0,:] = 2**16
#         self.visualized_image[1,:] = 2**16
#         self.visualized_image[:,0] = 2**16
#         self.visualized_image[:,1] = 2**16

#         self.visualized_image[self.eff_subarrayv+3,:] = 2**16
#         self.visualized_image[self.eff_subarrayv+2,:] = 2**16
#         self.visualized_image[:,self.eff_subarrayh+3] = 2**16
#         self.visualized_image[:,self.eff_subarrayh+2] = 2**16   
        try:
            
            #initialize position and velocity
            self.pi_hw.pidevice.VEL(1, 200)
            self.pi_hw.pidevice.MOV(1, self.pi_hw.home)
            
            #while the PI is moving, do nothing
            while any(list(self.pi_hw.pidevice.IsMoving(1).values())):
                pass
            
            
            self.camera.trsource.val = "internal"
            self.camera.sensor_mode.val = "progressive"
            
            self.camera.trsource.write_to_hardware()
            self.camera.sensor_mode.write_to_hardware()
            
            self.camera.read_from_hardware()
            
            self.camera.number_frames.val = 1
            self.camera.hamamatsu.bufferAlloc()
            
            while not self.interrupt_measurement_called:
            
                t1 = Thread(target=self.periodic_motion)
                t1.start()
            
                self.camera.hamamatsu.startAcquisitionWithoutAlloc()
                
                #print("time:", self.time2-self.camera.hamamatsu.time1)
                
                [frame, dims] = self.camera.hamamatsu.getLastFrame()
                self.np_data = frame.getData()
                self.image = np.reshape(self.np_data,(self.eff_subarrayv, self.eff_subarrayh))
                
                self.camera.hamamatsu.stopAcquisitionNotReleasing()
                    
                while self.is_pi_running:
                    pass
                
        finally:

            self.camera.hamamatsu.stopAcquisition()
            

    def update_display(self):
        """
        Displays the numpy array called self.image.  
        This function runs repeatedly and automatically during the measurement run,
        its update frequency is defined by self.display_update_period.
        """
        
#        self.visualized_image[2:self.eff_subarrayv+2, 2:self.eff_subarrayh+2]
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



    def periodic_motion(self):
        
        self.pi_hw.pidevice.VEL(1, abs(self.pi_hw.pp_amplitude.val)/self.camera.internal_frame_interval.val)
        
        print("Velocity we set: ", abs(self.pi_hw.pp_amplitude.val)/self.camera.internal_frame_interval.val)
        print("Velocity we get: ",self.pi_hw.pidevice.qVEL()['1'])
        
        self.is_pi_running = True
        
        assert 1 == len(self.pi_hw.pidevice.axes[1]), 'this sample requires one'

        STARTPOS = [self.pi_hw.home]
        
        #print(self.pi_hw.pidevice.qVEL())
        
        #print(self.pi_hw.pp_amplitude.val/self.camera.internal_frame_interval.val)
        #self.time2 = time.time()
        
        self.pi_hw.pidevice.MOV(1, STARTPOS[0]+self.pi_hw.pp_amplitude.val)
        
        while any(list(self.pi_hw.pidevice.IsMoving(1).values())):
            pass
        
        self.pi_hw.pidevice.VEL(1, 200)
        self.pi_hw.pidevice.MOV(1, STARTPOS[0])
        
        while any(list(self.pi_hw.pidevice.IsMoving(1).values())):
            pass
        
        self.pi_hw.pidevice.VEL(1, abs(self.pi_hw.pp_amplitude.val)/self.camera.internal_frame_interval.val)

        self.is_pi_running = False

#     def periodic_motion_old_old(self):
#         
#         self.is_pi_running = True
#         
#         assert 1 == len(self.pi_hw.pidevice.axes[1]), 'this sample requires one'
# 
# 
#         STARTPOS = [self.pi_hw.home]
#         AMPLITUDE = self.pi_hw.settings.pp_amplitude.val
#         NUMCYCLES = 1
#         NUMPOINTS = self.pi_hw.settings.number_of_points.val
#         TABLERATE = self.pi_hw.tablerate.val
#         SPEED_UP_DOWN = self.pi_hw.speed_up_down.val   #SLOW DOWN NUMBER OF POINTS
#         wavegens = (1,)
#         wavetables = (1,)
#         
#         print("TABLERATE:", TABLERATE)
#         print("NUMPOINTS:", NUMPOINTS)
#         print("SPEED_UP_DOWN:", SPEED_UP_DOWN)
#         print("AMPLITUDE:", AMPLITUDE)
#         print("STARTPOS[0]:", STARTPOS[0])
#         
#         self.pi_hw.pidevice.WAV_LIN(table=wavetables[0], firstpoint=1, numpoints=NUMPOINTS+100, append='X',
#                                       speedupdown=SPEED_UP_DOWN, amplitude=AMPLITUDE, offset=STARTPOS[0], seglength=NUMPOINTS+100)
#         
#         pitools.waitonready(self.pi_hw.pidevice)
#         
#         if self.pi_hw.pidevice.HasWSL():  
#             self.pi_hw.pidevice.WSL(wavegens, wavetables)
#         
#         if self.pi_hw.pidevice.HasWGC():
#             self.pi_hw.pidevice.WGC(wavegens, [NUMCYCLES] * len(wavegens))
#         
#         if self.pi_hw.pidevice.HasWTR():
#             self.pi_hw.pidevice.WTR(wavegens, [TABLERATE] * len(wavegens), interpol=[0] * len(wavegens))
#         
#         pitools.waitontarget(self.pi_hw.pidevice)
# 
#         self.pi_hw.pidevice.WGO(wavegens, mode=[1] * len(wavegens))
# 
#         while any(list(self.pi_hw.pidevice.IsGeneratorRunning(wavegens).values())):
#             
#             #time.sleep(0.01)
#             self.pi_hw.query_position()
#         
#         self.pi_hw.pidevice.WGO(wavegens, mode=[0] * len(wavegens))
#         
#         self.pi_hw.pidevice.MOV(1, STARTPOS[0])
#         
#         self.is_pi_running = False
#     

#     def periodic_motion_old(self):
#         
#         #self.is_pi_running = True
#         
#         assert 1 == len(self.pi_hw.pidevice.axes[1]), 'this sample requires one'
# 
#         STARTPOS = [self.pi_hw.home]
#         print(self.pi_hw.pidevice.qVEL())
#         
#         print(self.pi_hw.pp_amplitude.val/self.camera.internal_frame_interval.val)
#         
#         #time.sleep(0.72)
#         self.time2 = time.time()
#         self.pi_hw.pidevice.MOV(1, STARTPOS[0]+self.pi_hw.pp_amplitude.val)
#         #t1 = Thread(target = self.pi_hw.query_position)
#         #t1.start()
#         #time.sleep(3)
#         STARTPOS[0] = self.pi_hw.home
#         print('I am going hoooomeeee')
#         self.pi_hw.pidevice.MOV(1, STARTPOS[0])
#         print('finished')
#         #self.pi_hw.pidevice.MOV(1, STARTPOS[0])
#         #self.is_pi_running = False
#     def run_old(self):
#         
#         self.eff_subarrayh = int(self.camera.subarrayh.val/self.camera.binning.val)
#         self.eff_subarrayv = int(self.camera.subarrayv.val/self.camera.binning.val)
#         
#         self.image = np.zeros((self.eff_subarrayv,self.eff_subarrayh),dtype=np.uint16)
#         
#         self.image[0,0] = 1 #Otherwise we get the "all zero pixels" error (we should modify pyqtgraph...)
#         self.image[self.eff_subarrayv-1,0] = 1
#         self.image[0,self.eff_subarrayh-1] = 1
#         self.image[self.eff_subarrayv-1,self.eff_subarrayh-1] = 1
#         
#         self.visualized_image = np.zeros((self.eff_subarrayv,self.eff_subarrayh),dtype=np.uint16)
#         self.visualized_image[0,0] = 1 #Otherwise we get the "all zero pixels" error (we should modify pyqtgraph...)
#         
#         try:
#             self.pi_hw.pidevice.VEL(1, abs(self.pi_hw.pp_amplitude.val)/self.camera.internal_frame_interval.val)
#             self.pi_hw.pidevice.MOV(1, self.pi_hw.home)
#             self.camera.trsource.val = "internal"
#             self.camera.sensor_mode.val = "progressive"
#             
#             self.camera.trsource.write_to_hardware()
#             self.camera.sensor_mode.write_to_hardware()
#             
#             self.camera.number_frames.val = 1
#             
#             #while not self.interrupt_measurement_called:
#                 
#             t1 = Thread(target=self.periodic_motion)
#             t1.start()
#             
# 
#             self.camera.hamamatsu.startAcquisition()
#             #print("time:", self.time2-self.camera.hamamatsu.time1)
#             [frame, dims] = self.camera.hamamatsu.getLastFrame()
#             self.np_data = frame.getData()
#             self.image = np.reshape(self.np_data,(self.eff_subarrayv, self.eff_subarrayh))
#             
#             self.camera.hamamatsu.stopAcquisition()
#                 
#                 #while self.is_pi_running:
#                 #    pass
#                 
#         finally:
# 
#             self.camera.hamamatsu.stopAcquisition()
#             
#     def tryMovement_old(self):
#         
#         assert 1 == len(self.pi_hw.pidevice.axes[1]), 'this sample requires one'
#         
#         STARTPOS = [self.pi_hw.home]
#         
#         AMPLITUDE= self.pi_hw.settings.pp_amplitude.val
#         NUMCYCLES = 7
#         wavegens = (1,)
#         wavetables = (1,)
#         NUMPOINTS = int(self.pi_hw.number_of_points.val)
#         TABLERATE = int(self.pi_hw.tablerate.val)
#         SPEED_UP_DOWN = float(self.pi_hw.speed_up_down.val)
#         
#         print('define ramp waveforms for wave tables {}'.format(wavetables))
#         self.pi_hw.pidevice.WAV_LIN(table=wavetables[0], firstpoint=0, numpoints=NUMPOINTS, append='X',
#                                       speedupdown=SPEED_UP_DOWN, amplitude=AMPLITUDE, offset=STARTPOS[0], seglength=NUMPOINTS)
#         pitools.waitonready(self.pi_hw.pidevice)
#         if self.pi_hw.pidevice.HasWSL():  # you can remove this code block if your controller does not support WSL()
#             print('connect wave generators {} to wave tables {}'.format(wavegens, wavetables))
#             self.pi_hw.pidevice.WSL(wavegens, wavetables)
#         if self.pi_hw.pidevice.HasWGC():  # you can remove this code block if your controller does not support WGC()
#             print('set wave generators {} to run for {} cycles'.format(wavegens, NUMCYCLES))
#             self.pi_hw.pidevice.WGC(wavegens, [NUMCYCLES] * len(wavegens))
#         if self.pi_hw.pidevice.HasWTR():  # you can remove this code block if your controller does not support WTR()
#             print('set wave table rate to {} for wave generators {}'.format(TABLERATE, wavegens))
#             self.pi_hw.pidevice.WTR(wavegens, [TABLERATE] * len(wavegens), interpol=[0] * len(wavegens))
#             print(TABLERATE)
#             
#         startpos = (STARTPOS[0])
#         print('move axes {} to their start positions {}'.format(self.pi_hw.pidevice.axes[1], startpos))
#         #self.pi_hw.pidevice.MOV(1, startpos)  # 1 is for the axes to be moved
#         pitools.waitontarget(self.pi_hw.pidevice)
#         print('start wave generators {}'.format(wavegens))
#         self.pi_hw.pidevice.WGO(wavegens, mode=[1] * len(wavegens))
#         print('\nreset wave generators {}'.format(wavegens))
#         while any(list(self.pi_hw.pidevice.IsGeneratorRunning(wavegens).values())):
#             #print('.', end='')
#             self.pi_hw.query_position()
#         self.pi_hw.pidevice.WGO(wavegens, mode=[0] * len(wavegens))
#         print('done')
#         
#         STARTPOS[0] = self.pi_hw.home
#         print('I am going hoooomeeee')
#         self.pi_hw.pidevice.MOV(1, STARTPOS[0])
#         print('finished')
#         
#     def tryMovement(self):
#         
#         #self.is_pi_running = True
#         
#         assert 1 == len(self.pi_hw.pidevice.axes[1]), 'this sample requires one'
# 
#         STARTPOS = [self.pi_hw.home]
#         
#         self.pi_hw.pidevice.VEL(1, self.pi_hw.pp_amplitude.val/self.camera.internal_frame_interval.val)
#         self.pi_hw.pidevice.MOV(1, STARTPOS[0]+self.pi_hw.pp_amplitude.val)
#         
#         time.sleep(1)
#         self.pi_hw.pidevice.MOV(1, STARTPOS[0])
#         #self.is_pi_running = False
#        
#     def calculatePiParameters(self):
#         
#         effective_frame_interval = self.camera.exposure_time.val + (self.camera.subarrayh.val + 10) * self.camera.internal_line_interval.val
#         print(effective_frame_interval)
#         number_of_points = self.pi_hw.settings.number_of_points.val
#         pi_table_point_duration = 200*10**-6
#         
#         self.pi_hw.calculated_tablerate = int(effective_frame_interval/(number_of_points*pi_table_point_duration))
#         self.pi_hw.tablerate.read_from_hardware()
#         self.pi_hw.calculated_speed_up_down = 100
#         self.pi_hw.speed_up_down.read_from_hardware()
    