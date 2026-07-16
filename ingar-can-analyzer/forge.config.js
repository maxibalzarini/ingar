'use strict';

module.exports = {
  packagerConfig: {
    asar: true,
    name: 'INGAR_CAN_ANALYZER',
    executableName: 'INGAR_CAN_ANALYZER',
    appCopyright: '© 2026 INGAR Consulting',
    win32metadata: {
      CompanyName: 'INGAR Consulting',
      FileDescription: 'INGAR CAN Analyzer',
      ProductName: 'INGAR CAN Analyzer',
      InternalName: 'INGAR_CAN_ANALYZER',
      OriginalFilename: 'INGAR_CAN_ANALYZER.exe'
    }
  },
  rebuildConfig: {},
  makers: [
    {
      name: '@electron-forge/maker-squirrel',
      config: {
        name: 'INGARCANAnalyzer',
        authors: 'INGAR Consulting',
        description: 'Aplicación HTML5 de escritorio para la plataforma INGAR CAN Analyzer.',
        setupExe: 'INGAR_CAN_ANALYZER_Setup.exe',
        noMsi: true
      }
    },
    {
      name: '@electron-forge/maker-zip',
      platforms: ['win32']
    }
  ]
};
