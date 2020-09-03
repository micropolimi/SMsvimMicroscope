from ScopeFoundry import BaseMicroscopeApp
import os
from qtpy import QtCore, QtGui, QtWidgets
from ScopeFoundry.helper_funcs import confirm_on_close, sibling_path
try:
    import configparser
except: # python 2
    import ConfigParser as configparser
    
class BaseMicroscopeAppModified(BaseMicroscopeApp):
    
    name = 'HamamatsuApp'
    
    def __init__(self, *kwds): 
        """
        We need an __init__ since we want to put a new save directory 
        """
        
        super().__init__(*kwds) # *kwds is needed since in the main we pass as argument sys.argv. Without
                                # the *kwds this will give a problem
        
        #self.settings.save_dir.update_value(QtWidgets.QFileDialog.getExistingDirectory(directory = "D:\\Data\\temp"))
        self.settings['save_dir'] = "D:\\data\\DMD\\temp" #PUT ALWAYS TWO SLASHES!!!!
        self.settings.save_dir.hardware_set_func = self.setDirFunc #calls set dir func when the save_dir widget is changed
    
#     def setup_default_ui(self, *kwds):
#         
#         super().setup_default_ui(*kwds)
#         self.ui.action_set_data_dir.triggered.connect(self.file_browser)
#         self.connect_to_browse_widgets(self.ui.save_dir_lineEdit, self.ui.save_dir_browse_pushButton)
    def setup_default_ui(self):
        
        """
        This function has been redefined just for adding the ability to 
        open the selected folder! Otherwise it opens the project folder.
        """
        self.ui.show()
        self.ui.activateWindow()
                
        """Loads various default features into the user interface upon app startup."""
        confirm_on_close(self.ui, title="Close %s?" % self.name, message="Do you wish to shut down %s?" % self.name, func_on_close=self.on_close)
        
        self.ui.hardware_treeWidget.setColumnWidth(0,175)
        self.ui.measurements_treeWidget.setColumnWidth(0,175)

        self.ui.measurements_treeWidget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.ui.measurements_treeWidget.customContextMenuRequested.connect(self.on_measure_tree_context_menu)

        self.ui.hardware_treeWidget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.ui.hardware_treeWidget.customContextMenuRequested.connect(self.on_hardware_tree_context_menu)

        # Add log widget to mdiArea
        self.logging_subwin = self.add_mdi_subwin(self.logging_widget, "Log")
        self.console_subwin = self.add_mdi_subwin(self.console_widget, "Console")
        
        # Setup the Measurement UI's         
        for name, measure in self.measurements.items():
            self.log.info("setting up figures for {} measurement {}".format( name, measure.name) )            
            measure.setup_figure()
            if self.mdi and hasattr(measure, 'ui'):
                subwin = self.add_mdi_subwin(measure.ui, measure.name)
                measure.subwin = subwin
        
        if hasattr(self.ui, 'console_pushButton'):
            self.ui.console_pushButton.clicked.connect(self.console_widget.show)
            self.ui.console_pushButton.clicked.connect(self.console_widget.activateWindow)
                        
        if self.quickbar is None:
            # Collapse sidebar
            self.ui.quickaccess_scrollArea.setVisible(False)
        
        
        # Save Dir events
        #=======================================================================
        #Only this part has been modified
        
        self.ui.action_set_data_dir.triggered.connect(self.file_browser)
        self.connect_to_browse_widgets(self.ui.save_dir_lineEdit, self.ui.save_dir_browse_pushButton)
        
        #=======================================================================
        # Sample meta data
        self.settings.sample.connect_bidir_to_widget(self.ui.sample_lineEdit)
        
        #settings button events
        if hasattr(self.ui, "settings_autosave_pushButton"):
            self.ui.settings_autosave_pushButton.clicked.connect(self.settings_auto_save_ini)
        if hasattr(self.ui, "settings_load_last_pushButton"):
            self.ui.settings_load_last_pushButton.clicked.connect(self.settings_load_last)
        if hasattr(self.ui, "settings_save_pushButton"):
            self.ui.settings_save_pushButton.clicked.connect(self.settings_save_dialog)
        if hasattr(self.ui, "settings_load_pushButton"):
            self.ui.settings_load_pushButton.clicked.connect(self.settings_load_dialog)
        
        #Menu bar entries:
        # TODO: connect self.ui.action_log_viewer to log viewer function
            # (Function has yet to be created)
        self.ui.action_load_ini.triggered.connect(self.settings_load_dialog)
        self.ui.action_auto_save_ini.triggered.connect(self.settings_auto_save_ini)
        self.ui.action_save_ini.triggered.connect(self.settings_save_dialog)
        self.ui.action_console.triggered.connect(self.console_widget.show)
        self.ui.action_console.triggered.connect(self.console_widget.activateWindow)
        
        
        #Refer to existing ui object:
        self.menubar = self.ui.menuWindow

        #Create new action group for switching between window and tab mode
        self.action_group = QtWidgets.QActionGroup(self)
        #Add actions to group:
        self.action_group.addAction(self.ui.window_action)
        self.action_group.addAction(self.ui.tab_action)
        
        self.ui.mdiArea.setTabsClosable(False)
        self.ui.mdiArea.setTabsMovable(True)
        
        self.ui.tab_action.triggered.connect(self.set_tab_mode)
        self.ui.window_action.triggered.connect(self.set_subwindow_mode)
        self.ui.cascade_action.triggered.connect(self.cascade_layout)
        self.ui.tile_action.triggered.connect(self.tile_layout)
        
        self.ui.setWindowTitle(self.name)

        # Set Icon
        logo_icon = QtGui.QIcon(sibling_path(__file__, "scopefoundry_logo2_1024.png"))
        self.qtapp.setWindowIcon(logo_icon)
        self.ui.setWindowIcon(logo_icon)    
    
    def setDirFunc(self, val = None):
        """
        Gets called every time we modify the directory.
        If it does not exist, we create a new one
        """
        
        if not os.path.isdir(self.settings['save_dir']):
            os.makedirs(self.settings['save_dir'])
    
    def file_browser(self):

        if self.settings.save_dir.is_dir:
            fname = QtWidgets.QFileDialog.getExistingDirectory(directory = self.settings.save_dir.val)
        else:
            fname, _ = QtWidgets.QFileDialog.getOpenFileName(directory = self.settings.save_dir.val)
        self.settings.save_dir.log.debug(repr(fname))
        if fname:
            self.settings.save_dir.update_value(fname)
      
    def connect_to_browse_widgets(self, lineEdit, pushButton):
        assert type(lineEdit) == QtWidgets.QLineEdit
        self.settings.save_dir.connect_to_widget(lineEdit)
      
        assert type(pushButton) == QtWidgets.QPushButton
        pushButton.clicked.connect(self.file_browser)

#     def settings_load_ini(self, fname):
#         """
#         ==============  =========  ==============================================
#         **Arguments:**  **Type:**  **Description:**
#         fname           str        relative path to the filename of the ini file.              
#         ==============  =========  ==============================================
#         """
# 
#         self.log.info("ini settings loading from {}".format(fname))
#         config = configparser.ConfigParser(interpolation=None)
#         #config = configparser.ConfigParser()
#         config.optionxform = str
#         config.read(fname)
# 
#         if 'app' in config.sections():
#             for lqname, new_val in config.items('app'):
#                 lq = self.settings.get_lq(lqname)
#                 lq.update_value(new_val)
#         
#         for hc_name, hc in self.hardware.items():
#             section_name = 'hardware/'+hc_name
#             self.log.info(section_name)
#             if section_name in config.sections():
#                 for lqname, new_val in config.items(section_name):
#                     try:
#                         lq = hc.settings.get_lq(lqname)
#                         if not lq.ro:
#                             lq.update_value(new_val)
#                     except Exception as err:
#                         self.log.info("-->Failed to load config for {}/{}, new val {}: {}".format(section_name, lqname, new_val, repr(err)))
#                         
#         for meas_name, measurement in self.measurements.items():
#             section_name = 'measurement/'+meas_name            
#             if section_name in config.sections():
#                 for lqname, new_val in config.items(section_name):
#                     try:
#                         lq = measurement.settings.get_lq(lqname)
#                         if not lq.ro:
#                             lq.update_value(new_val)
#                     except Exception as err:
#                         self.log.info("-->Failed to load config for {}/{}, new val {}: {}".format(section_name, lqname, new_val, repr(err)))        
