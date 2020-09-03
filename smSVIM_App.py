from BaseMicroscopeAppModified import BaseMicroscopeAppModified

class smSVIM_App(BaseMicroscopeAppModified):
    '''
    Application for Spatially Modulated Selective Volume Illumination Microscopy using:
    Hamamatsu Flash 4.0 Camera
    PI C413 Voice coil motor
    DMD Texas Instrument DLP-6500
    
    '''
    name = 'smSVIM_App'
    
    def setup(self):
        
        from DMD_ScopeFoundry.DMDHardware import DmdHardware
        self.add_hardware(DmdHardware(self))
        
        from Hamamatsu_ScopeFoundry.CameraHardware import HamamatsuHardware
        self.add_hardware(HamamatsuHardware(self))
        
        from PI_ScopeFoundry.PICoilStageHardware import PIStageNew
        self.add_hardware(PIStageNew(self))    

        print("Adding Hardware Components")
        
        from Hamamatsu_ScopeFoundry.CameraMeasurement import HamamatsuMeasurement
        self.add_measurement(HamamatsuMeasurement(self))
        
        from smTriggered_Measurement import StructuredLightTriggeredMeasurement
        self.add_measurement(StructuredLightTriggeredMeasurement(self))
        
        from smSVIM_Measurement import SMsvimMeasurement
        self.add_measurement(SMsvimMeasurement(self))
        
        from smCalibration_Measurement import CalibrationMeasurement
        self.add_measurement(CalibrationMeasurement(self))
        
        print("Adding measurement components")
        
        self.ui.show()
        self.ui.activateWindow()
        

if __name__ == '__main__':
            
    import sys
    app = smSVIM_App(sys.argv)
    sys.exit(app.exec_())
        