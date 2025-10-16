# Deployment Guide - DigitalOcean App Platform

## Prerequisites
- DigitalOcean account
- GitHub repository with your code
- Credit card for DigitalOcean billing

## Step-by-Step Deployment

### 1. Push Code to GitHub
Make sure all files are committed and pushed:
```bash
git add .
git commit -m "Add deployment configuration"
git push origin master
```

### 2. Create App on DigitalOcean

1. **Go to App Platform**: https://cloud.digitalocean.com/apps
2. **Click "Create App"**
3. **Connect GitHub**:
   - Select "GitHub" as source
   - Authorize DigitalOcean to access your repos
   - Choose repository: `Eppsidy/TnCs-Scanner-backend`
   - Select branch: `master`
   - Enable "Autodeploy" (optional but recommended)

### 3. Configure Your App

#### App Info:
- **Name**: `tncs-scanner-backend` (or your preferred name)
- **Region**: Choose closest to your users (e.g., New York, San Francisco, London)

#### Resources:
DigitalOcean should auto-detect:
- **Type**: Web Service
- **Build Command**: `pip install -r requirements.txt`
- **Run Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

If not auto-detected, manually enter these values.

#### Environment Variables (Optional):
Click "Edit" next to Environment Variables and add:
- `SUMMARIZER_MODEL` = `sshleifer/distilbart-cnn-12-6` (default)
- `CHUNK_TOKEN_LIMIT` = `700` (default)
- `PYTHON_VERSION` = `3.11`

#### Instance Size:
⚠️ **IMPORTANT**: Due to the AI model size (~1GB), you'll need:
- **Minimum**: Professional (2GB RAM) - $12/month
- **Recommended**: Professional (4GB RAM) - $24/month

Basic tier (512MB RAM) will cause crashes due to the transformer model.

### 4. Deploy

1. Review your configuration
2. Click "Next" → "Create Resources"
3. Wait 5-10 minutes for initial deployment
4. DigitalOcean will:
   - Build your app
   - Download dependencies
   - Download NLTK data
   - Download the AI model (~1GB)
   - Start the service

### 5. Access Your API

Once deployed, you'll get a URL like:
```
https://tncs-scanner-backend-xxxxx.ondigitalocean.app
```

Test it:
```bash
curl https://your-app-url.ondigitalocean.app/health
```

## Environment Configuration

### CORS Settings
⚠️ **Production Security**: Update CORS in `main.py`:

Currently set to allow all origins (`"*"`). Change to:
```python
allow_origins=[
    "https://your-frontend-domain.com",
    "https://www.your-frontend-domain.com"
]
```

### Custom Domain (Optional)
1. Go to your app settings
2. Click "Domains"
3. Add your custom domain
4. Update DNS records as instructed

## Monitoring & Logs

### View Logs:
- Go to your app in DigitalOcean
- Click "Runtime Logs" tab
- See real-time application logs

### Performance:
- Monitor CPU and RAM usage in the "Insights" tab
- Set up alerts for high resource usage

## Costs

### Estimated Monthly Cost:
- **Professional (2GB RAM)**: $12/month
- **Professional (4GB RAM)**: $24/month
- **Bandwidth**: Included (100GB)

### Tips to Reduce Costs:
1. Use a smaller model if possible
2. Implement caching for frequent requests
3. Scale down during low-traffic periods

## Troubleshooting

### Common Issues:

**1. App crashes on startup**
- **Cause**: Insufficient memory for AI model
- **Fix**: Upgrade to Professional tier (2GB+ RAM)

**2. Slow cold starts**
- **Cause**: Model downloading on each deployment
- **Fix**: Consider using Docker with pre-loaded model (see Docker guide)

**3. NLTK data errors**
- **Cause**: Network issues during download
- **Fix**: Already handled in code with try/catch

**4. Timeout errors**
- **Cause**: Large file processing
- **Fix**: Increase timeout in App Platform settings or implement async processing

### Check Build Logs:
If deployment fails:
1. Go to "Build Logs" tab
2. Look for errors in package installation
3. Common fixes:
   - Update `requirements.txt` versions
   - Check Python version compatibility

## Updating Your App

### Automatic Deployment:
If "Autodeploy" is enabled, just push to GitHub:
```bash
git add .
git commit -m "Your changes"
git push origin master
```
DigitalOcean will automatically rebuild and deploy.

### Manual Deployment:
1. Go to your app in DigitalOcean
2. Click "Create Deployment"
3. Select branch and deploy

## Rollback

If a deployment breaks:
1. Go to "Deployments" tab
2. Find a working deployment
3. Click "Redeploy"

## Next Steps

1. Set up monitoring and alerts
2. Configure custom domain
3. Update CORS settings for production
4. Set up CI/CD for automated testing
5. Consider implementing rate limiting
6. Add authentication if needed

## Support

- DigitalOcean Docs: https://docs.digitalocean.com/products/app-platform/
- Community: https://www.digitalocean.com/community/
- Your app dashboard: https://cloud.digitalocean.com/apps

---

**Need help?** Check the DigitalOcean community forums or contact their support.
