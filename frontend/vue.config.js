// vue.config.js
const { defineConfig } = require('@vue/cli-service')

module.exports = defineConfig({
  transpileDependencies: true,
  devServer: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: 'all',

    proxy: {
      '/api': {
        target: 'http://backend:5001',
        changeOrigin: true,
        pathRewrite: { '^/api': '' }
      }
    }
  }
})
