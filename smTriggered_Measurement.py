""" 
-Michele Castriotta (@mikics on github), MSc at Politecnico di Milano;
-Andrea Bassi;
-Gianmaria Calisesi;

20/02/19
   
In this measurement class we can choose among two modalities: fixed length and run till abort.

In the run till abort mode, we just acquire images without saving.

In the fixed length mode, we load certain patterns on the dmd, and then the camera acquires images
when triggered by the dmd. To make a measurement, follow these steps:

0. Connect the trigger of the dmd to the camera, and switch on the devices.

1. Connect camera and dmd through the "connect" checkbox in the hardware classes of the devices.

2. Select an input directory, from which images will be fetched. If the folder contains .png images,
remember to name your images so that their last characters are a number, and so that the alphabetical order
reflects the order of visualization on the dmd. (see example_patterns folder) (the code is written considering ONLY .png images)
Then choose a starting point for your image (the number from which you want to start), a step (corresponding
to the numerical step between successive images), and a max number of images to show. For example, if you choose
as starting point 200, as step 5, and as max number 10, the first image to be shown on the dmd will be the one
that have as last number 200, then 205, 210, etc... Until you will reach the 10th and last image. 
If you want to use all the images, just check the "all" checkbox.
If you are using .encd file, put just one of this file in the input directory (with the correct encoding).
All the patterns are contained there.

3. Choose the expoosure time for the camera, the dimension of the images,
the fixed length mode, and the external triggering mode.

4. Choose the exposure time of each pattern (be careful to choose an exposure time greater than the exp time 
of the camera!), the mode 3 (that is the pattern on the fly mode), the bith depth, the dark time, and check
the trigger_output box.

5. Choose a correct destination for your .h5 data (Notice: there is no save_h5 checkbox; in fixed_length
mode the data will always be saved once the measurement is started).

6. Start the measurement!

7. Enjoy your data.

"""

from Hamamatsu_ScopeFoundry.CameraMeasurement import HamamatsuMeasurement
from DMD_ScopeFoundry.DMDDeviceHID import save_encoded_sequence
from qtpy import QtCore, QtWidgets
import os
import PIL.Image
from ScopeFoundry.helper_funcs import sibling_path, load_qt_ui_file
import numpy as np
import pyqtgraph as pg
import time

class StructuredLightTriggeredMeasurement(HamamatsuMeasurement):
    
    name = "Structured_light_measurement"
    
    def setup(self):
        
        self.previous_settings = {}
        self.ui_filename = sibling_path(__file__, "triggered.ui")
        
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
        self.settings.New("all", dtype = bool, si = False, ro = 0, initial = False)
        
        #self.manually = self.add_logged_quantity("manually", dtype = bool)
        """
        endswith settings removed. If you want to choose an extension, insert it again and change the points of the code where is present .png
        """
        #self.settings.New("endswith", dtype = str, si = False, ro = 0, initial = ".png")
        self.settings.New("starting_point", dtype = int, si = False, ro = 0, initial = "1")
        self.settings.New("step", dtype = int, si = False, ro = 0, initial = 1)
        self.settings.New("max_number", dtype = int, si = False, ro = 0, initial = 10)
        
        """
        To have the best coherence between different functions, I have created two directories settings.
        In fact many operations require an input folder (from which fetching data) and an output folder
        (in which saving data). Therefore one must decide from which directory fetching data and where saving data.
        """
        
        self.settings.New("input_directory", dtype = 'file', is_dir = True, 
                                               initial = "D:/LabPrograms/Python/DMD_Pattern/encd_Patterns/multiple_Pattern_Encoding_SVIMMeasurement/encd_bin_Alternated_Hadamard_128Pixel/")
        self.settings.New("output_directory", dtype = 'file', is_dir = True, 
                                               initial = "D:/LabPrograms/Python/DMD_Pattern/encd_Patterns/")
        """
        
        """
#        self.settings.New("run_encoded_pattern", dtype = bool, si = False, ro = 0)
#         self.settings.New("file_settings", dtype = 'file', is_dir = False,
#                                                initial = "E:\\LabPrograms\\Python\\LSFM_ScopeFoundry\\settings")
        self.add_operation("input_browser", self.input_file_browser)
        self.add_operation("output_browser", self.output_file_browser)
        self.add_operation("load_sequence", self.load_sequence)
        self.add_operation("start_sequence", self.start_sequence)
#         self.add_operation("pause_sequence", self.pause_sequence)
        self.add_operation("stop_sequence", self.stop_sequence)
#         self.add_operation("save_settings", self.save_settings)
#         self.add_operation("load_settings", self.load_settings)
        self.add_operation("encode_sequence", self.encode_sequence)
        self.add_operation("encode_single_images", self.encode_single_images)
        
        self.add_operation("reset_dmd", self.reset_dmd)
        
        self.camera = self.app.hardware['HamamatsuHardware']
        self.dmd_hw = self.app.hardware["DmdHardware"]
        
        self.autoRange = self.settings.autoRange.val
        self.display_update_period = self.settings.refresh_period.val
        self.autoLevels = self.settings.autoLevels.val
        self.level_min = self.settings.level_min.val
        self.level_max = self.settings.level_max.val
#         print(self.ui.autoLevels_checkBox.isChecked())
#         print(self.ui.max_doubleSpinBox.value())
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
        self.camera.settings.frame_exposure_time.connect_to_widget(self.ui.frame_exposure_time_doubleSpinBox)
        self.camera.settings.exposure_time.connect_to_widget(self.ui.exposure_time_doubleSpinBox)
        self.camera.settings.internal_line_interval.connect_to_widget(self.ui.internal_line_interval_doubleSpinBox)
        self.camera.settings.sensor_mode.connect_to_widget(self.ui.sensor_mode_comboBox)
        
        self.dmd_hw.settings.connected.connect_to_widget(self.ui.connected_checkBox_2)
        self.dmd_hw.settings.exposure.connect_to_widget(self.ui.exposure_doubleSpinBox)
        self.settings.input_directory.connect_to_widget(self.ui.input_directory_lineEdit)
        self.settings.progress.connect_to_widget(self.ui.progress_progressBar)
        self.settings.all.connect_to_widget(self.ui.all_checkBox)
        self.settings.starting_point.connect_to_widget(self.ui.starting_point_doubleSpinBox)
        self.settings.step.connect_to_widget(self.ui.step_doubleSpinBox)
        self.settings.max_number.connect_to_widget(self.ui.max_number_doubleSpinBox)
        self.settings.rotate_image.connect_to_widget(self.ui.rotate_image_comboBox)
        self.ui.search_pushButton.clicked.connect(self.input_file_browser)
        # Set up pyqtgraph graph_layout in the UI
        self.imv = pg.ImageView()
        self.ui.plot_groupBox.layout().addWidget(self.imv)
        
        # Image initialization
        self.image = np.zeros((int(self.camera.subarrayv.val),int(self.camera.subarrayh.val)),dtype=np.uint16)
        self.image[0,0] = 1 
        
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
            
    def taking_patterns(self):
        
        self.camera.read_from_hardware()
        self.dmd_hw.read_from_hardware()
        input_directory_in_str = self.settings.input_directory.val
        input_directory = os.fsencode(input_directory_in_str)
        
        check_file = sorted(os.listdir(input_directory))[0] #this variable is used for checking if the files to load are images or encoded files
        check_file = os.fsdecode(check_file)
        
        patterns=[]
        
        if check_file.endswith(".txt"):
            check_file = sorted(os.listdir(input_directory))[1]
            
        if check_file.endswith(".png"):
            #if the file is an image, and not an encoded file (I assume to work only with these two kinds of format)
            extension = "png"
            
            if self.settings.all.val:
                for file in sorted(os.listdir(input_directory)):
                    filename = os.fsdecode(file)
                    arr = np.array(PIL.Image.open(input_directory_in_str+filename), dtype = np.bool)
                    patterns.append(arr)
            
            else:
                starting_point = self.settings.starting_point.val
                step = self.settings.step.val
                for file in sorted(os.listdir(input_directory)):
                    filename = os.fsdecode(file)
                    """
                    The code works only if the format is png. Other formats can be added
                    with a simple "or" or a settings in which you specify the format.
                    """     
                    if filename.endswith(str(starting_point) + ".png"):
                        """
                        Here is necessary to specify the array as boolean, since, otherwise, python
                        sees an 8 bit image, adn, when we merge patterns, there are overflow issues, besides
                        of issues in adding patterns. With boolean, I think, Python automatically transforms
                        the image in a "boolean" image.
                        """
                        arr = np.array(PIL.Image.open(input_directory_in_str+filename), dtype = np.bool)
                        patterns.append(arr)
                        starting_point = starting_point + step
    
                    if len(patterns) >= self.settings.max_number.val:
                        break
                    
        else: #if we have encoded patterns
            
            extension = "encd"
            
            for file in sorted(os.listdir(input_directory)): #actually I expect only one file. so the "for" lasts one cycle
                filename = os.fsdecode(file)
                arr = filename
                patterns.append(arr)
        
        return patterns, extension
    
    def run(self):
        
        self.eff_subarrayh = int(self.camera.subarrayh.val/self.camera.binning.val)
        self.eff_subarrayv = int(self.camera.subarrayv.val/self.camera.binning.val)
        
        self.image = np.zeros((self.eff_subarrayv,self.eff_subarrayh),dtype=np.uint16)
        
        self.image[0,0] = 1 #Otherwise we get the "all zero pixels" error (we should modify pyqtgraph...)
        self.image[self.eff_subarrayv-1,0] = 1
        self.image[0,self.eff_subarrayh-1] = 1
        self.image[self.eff_subarrayv-1,self.eff_subarrayh-1] = 1
        try:
            
            self.camera.trsource.update_value(new_val = 'external')
                            
            exposure=[self.dmd_hw.exposure.val]
            dark_time=[self.dmd_hw.dark_time.val]
            trigger_input=[self.dmd_hw.trigger_input.val]
            trigger_output=[True]
                
            index = 0
            
            patterns = []
            patterns, extension = self.taking_patterns()
                
            if extension == "png": 
                    
                first = 0
                        
                while index < len(patterns):
                        
                    if first == 0:
                        
                        exposure=exposure*len(patterns)
                        dark_time=dark_time*len(patterns)
                        trigger_input=trigger_input*len(patterns)
                        trigger_output=trigger_output*len(patterns)
                        
                        self.camera.hamamatsu.number_frames = len(patterns)
                        self.camera.settings.number_frames.val = len(patterns)
                        self.initH5()
                        print("\n \n ******* \n \n Saving :D !\n \n *******")
                        first = 1
                        self.dmd_hw.dmd.defsequence(patterns,exposure,trigger_input,dark_time,trigger_output,0)
                        self.camera.hamamatsu.startAcquisition()
                        time.sleep(0.1)
                        self.dmd_hw.dmd.startsequence()
        
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
                    self.settings['progress'] = index*100./len(patterns)
                    
                self.dmd_hw.dmd.stopsequence()
                self.camera.hamamatsu.stopAcquisition()
                    
                        
            else: #if we have encoded images
                
                index = 0 #I dont think it's necessary
                first = 0
                finished = False
                  
                while not finished:
                    
                    if first == 0:
                        
                        number_patterns = self.dmd_hw.dmd.def_sequence_by_file(self.settings.input_directory.val + patterns[0], exposure, trigger_input, dark_time, trigger_output, 0)
                        self.camera.hamamatsu.number_frames = number_patterns
                        self.camera.settings.number_frames.val = number_patterns
                        self.camera.hamamatsu.startAcquisition()
                        self.dmd_hw.dmd.startsequence()
                        
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
                    self.settings['progress'] = index*100./number_patterns
                    
                    if index >= number_patterns:
                        finished = True
                    
                self.dmd_hw.dmd.stopsequence()
                self.camera.hamamatsu.stopAcquisition()
                    
        finally:
            
            self.camera.hamamatsu.stopAcquisition()
            self.dmd_hw.dmd.stopsequence()
            if self.camera.acquisition_mode.val == "fixed_length":
                self.h5file.close()

    @QtCore.Slot()    
    def input_file_browser(self):
        """
        Opens a dialog when click on browser, and update the value of the input_directory
        from which fetching patterns.
        """
#         
        if self.settings.input_directory.is_dir:
            fname = QtWidgets.QFileDialog.getExistingDirectory(directory = self.settings.input_directory.val[:-1])
        else:
            fname, _ = QtWidgets.QFileDialog.getOpenFileName(directory = self.settings.input_directory.val[:-1])
            
        self.settings.input_directory.log.debug(repr(fname))
        self.settings.input_directory.update_value(fname + "/")
               
    @QtCore.Slot()    
    def output_file_browser(self):
        """
        Opens a dialog when click on browser, and update the value of the output_directory
        for saving data.
        """

        if self.settings.output_directory.is_dir:
            fname = QtWidgets.QFileDialog.getExistingDirectory(directory = self.settings.output_directory.val[:-1])
        else:
            fname, _ = QtWidgets.QFileDialog.getOpenFileName(directory = self.settings.output_directory.val[:-1])
            
        self.settings.output_directory.log.debug(repr(fname))
        self.settings.output_directory.update_value(fname + "/")


    @QtCore.Slot()
    def load_sequence(self):
        """
        Load a sequence of images as a patterns sequence. It takes the images from the input_directory.
        The code is supposed to work with a folder containing images ending with a number, and
        the sorted list has the same sorting of these final number. Be careful that for the function 
        sorted() the files are sorted considering the first digit of the final number, therefore if 
        the file ends with 200 this will be later in the list with respect a file ending with 1400.
        
        So put, as final number, always the same number of digits. If some digits are not necessary,
        put zeroes before (for example 0200 instead of 200 if you have max four digits).
        
        Then the sequence is loaded respecting the first value to fetch (starting_point), the step between
        numbers, and the max number of images in the pattern.
        """
        images=[]
    
        input_directory_in_str = self.settings.input_directory.val
        input_directory = os.fsencode(input_directory_in_str)
        if self.settings.all.val:
            for file in sorted(os.listdir(input_directory)):
                filename = os.fsdecode(file)
                arr = np.array(PIL.Image.open(input_directory_in_str+filename), dtype = np.bool)
                images.append(arr)
        
        else:
            starting_point = self.settings.starting_point.val
            step = self.settings.step.val
            for file in sorted(os.listdir(input_directory)):
                filename = os.fsdecode(file)     
                if filename.endswith(str(starting_point) + ".png"):
                    """
                    Here is necessary to specify the array as boolean, since, otherwise, python
                    sees an 8 bit image, adn, when we merge images, there are overflow issues, besides
                    of issues in adding patterns. With boolean, I think, Python automatically transforms
                    the image in a "boolean" image.
                    """
                    arr = np.array(PIL.Image.open(input_directory_in_str+filename), dtype = np.bool)
                    images.append(arr)
                    starting_point = starting_point + step

                if len(images) >= self.settings.max_number.val:
                    break
                
        exposure=[self.dmd_hw.exposure.val]*len(images)
        dark_time=[self.dmd_hw.dark_time.val]*len(images)
        trigger_input=[self.dmd_hw.trigger_input.val]*len(images)
        trigger_output=[self.dmd_hw.trigger_output.val]*len(images)
        
        self.dmd_hw.dmd.defsequence(images,exposure,trigger_input,dark_time,trigger_output,0)
        print("****************\n\nStop Loading sequence!\n\n****************")
    
    
    @QtCore.Slot()
    def encode_sequence(self):
        """
        Encode a sequence of images, that will be used for a pattern sequence.
        You can choose if encode them all, or just a few, by properly selecting
        the number for the first image, the step for the successive images
        """
        images=[]
        
        input_directory_in_str = self.settings.input_directory.val
        input_directory = os.fsencode(input_directory_in_str)
        if self.settings.all.val:
            for file in sorted(os.listdir(input_directory)):
                filename = os.fsdecode(file)
                if filename.endswith(".png"):
                    arr = np.array(PIL.Image.open(input_directory_in_str+filename), dtype = np.bool)
                    images.append(arr)
        
        else:
            starting_point = self.settings.starting_point.val
            step = self.settings.step.val
            for file in sorted(os.listdir(input_directory)):
                filename = os.fsdecode(file)     
                if filename.endswith(str(starting_point) + ".png"):
                    """
                    Here is necessary to specify the array as boolean, since, otherwise, python
                    sees an 8 bit image, adn, when we merge images, there are overflow issues, besides
                    of issues in adding patterns. With boolean, I think, Python automatically transforms
                    the image in a "boolean" image.
                    """
                    arr = np.array(PIL.Image.open(input_directory_in_str+filename), dtype = np.bool)
                    images.append(arr)
                    starting_point = starting_point + step

                if len(images) >= self.settings.max_number.val:
                    break
                
        save_encoded_sequence(images, self.settings.output_directory.val, "0001")
 
        print("****************\n\nStop Encoding sequence!\n\n****************")
    
    
    @QtCore.Slot()
    def load_encoded_sequence(self):
        """
        Load an encoded sequence (stored in a single file).
        """

        fname, _ = QtWidgets.QFileDialog.getOpenFileName(directory = self.settings.input_directory.val)    
        exposure = self.dmd_hw.exposure.val
        dark_time = self.dmd_hw.dark_time.val
        trigger_input = self.dmd_hw.trigger_input.val
        trigger_output = self.dmd_hw.trigger_output.val
        
        self.dmd_hw.dmd.def_sequence_by_file(fname, exposure, dark_time, trigger_input, trigger_output, 0)
        print("****************\n\nStop Loading sequence!\n\n****************")

    @QtCore.Slot()
    def encode_single_images(self):
        """
        Encode a sequence of images, that will be used for a pattern sequence.
        You can choose if encode them all, or just a few, by properly selecting
        the number for the first image, the step for the successive images
        """
           
        input_directory_in_str = self.settings.input_directory.val
        input_directory = os.fsencode(input_directory_in_str)
        index = 0
        
        number_images = len(sorted(os.listdir(input_directory)))
        number_images_str = str(number_images)
        len_number_images_str = len(number_images_str) #how many digits contain the number of images
        
        for file in sorted(os.listdir(input_directory)):
            index += 1
            len_index_str = len(str(index))
            
            """
            In order to have an ordering within the folder, the number of zeroes to put in the name must be decided,
            otherwise the ordering of the encoded images is not correct
            """
            number_zeroes = len_number_images_str - len_index_str 
            filename = os.fsdecode(file)
            if filename.endswith(".png"):
                arr = np.array(PIL.Image.open(input_directory_in_str+filename), dtype = np.bool)
                arr_list = [arr]
                save_encoded_sequence(arr_list, self.settings.output_directory.val, "0"*number_zeroes + str(index))
 
        print("****************\n\nStop Encoding sequence!\n\n****************")
      
    @QtCore.Slot()
    def start_sequence(self):

        self.dmd_hw.dmd.startsequence()
        
        print("****************\n\nThe sequence starts!\n\n****************")
    
    @QtCore.Slot()      
    def pause_sequence(self):

        self.dmd_hw.dmd.pausesequence()
        print("****************\n\nThe sequence pauses!\n\n****************")
    
    @QtCore.Slot()    
    def stop_sequence(self):

        self.dmd_hw.dmd.stopsequence()

        print("****************\n\nThe sequence stops!\n\n****************")
        
    @QtCore.Slot()    
    def reset_dmd(self):

        self.dmd_hw.dmd.reset()

        print("****************\n\nDevice Resetted!\n\n****************")
        