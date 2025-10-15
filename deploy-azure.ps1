# Azure Container Registry and Container App Deployment Script (PowerShell)
# Usage: .\deploy-azure.ps1

# Configuration (change these to your values)
$RESOURCE_GROUP = "tncs-scanner-backend"
$LOCATION = "southafricanorth" 
$ACR_NAME = "tncsscanner2025"  # Must be globally unique, lowercase, no hyphens
$CONTAINER_APP_NAME = "tncs-scanner-api"
$CONTAINER_APP_ENV = "tncs-scanner-env"
$IMAGE_NAME = "tncs-scanner-backend"
$TAG = "latest"

Write-Host "[*] Starting Azure deployment..." -ForegroundColor Green
Write-Host "NOTE: Providers already registered, skipping step 0" -ForegroundColor Yellow

# 1. Create resource group
Write-Host "[1/7] Creating resource group..." -ForegroundColor Cyan
az group create --name $RESOURCE_GROUP --location $LOCATION

# 2. Create Azure Container Registry
Write-Host "[2/7] Creating Azure Container Registry..." -ForegroundColor Cyan
az acr create `
  --resource-group $RESOURCE_GROUP `
  --name $ACR_NAME `
  --sku Basic `
  --admin-enabled true

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to create Container Registry" -ForegroundColor Red
    exit 1
}

# 3. Push local image to ACR (with chunked upload for large images)
Write-Host "[3/7] Logging into ACR..." -ForegroundColor Cyan
az acr login --name $ACR_NAME

Write-Host "[3/7] Pushing Docker image to ACR (this may take 10-20 minutes for 7GB image)..." -ForegroundColor Cyan
Write-Host "If this fails, you can alternatively build directly in Azure (slower but more reliable)" -ForegroundColor Yellow

$ACR_LOGIN_SERVER = az acr show --name $ACR_NAME --query loginServer --output tsv
docker tag tncs-scanner-backend:latest "${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${TAG}"

# Push with retry logic
$maxRetries = 3
$retryCount = 0
$pushed = $false

while (-not $pushed -and $retryCount -lt $maxRetries) {
    if ($retryCount -gt 0) {
        Write-Host "Retry attempt $retryCount of $maxRetries..." -ForegroundColor Yellow
    }
    
    docker push "${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${TAG}"
    
    if ($LASTEXITCODE -eq 0) {
        $pushed = $true
        Write-Host "Image pushed successfully!" -ForegroundColor Green
    } else {
        $retryCount++
        if ($retryCount -lt $maxRetries) {
            Write-Host "Push failed, retrying in 10 seconds..." -ForegroundColor Yellow
            Start-Sleep -Seconds 10
        }
    }
}

if (-not $pushed) {
    Write-Host "ERROR: Failed to push image after $maxRetries attempts" -ForegroundColor Red
    Write-Host "The image is too large (7.37GB) for reliable upload." -ForegroundColor Yellow
    Write-Host "" 
    Write-Host "ALTERNATIVE SOLUTION:" -ForegroundColor Cyan
    Write-Host "1. Use a smaller model (reduces image to ~2GB)" -ForegroundColor White
    Write-Host "2. Build directly on Azure (upload source instead of image)" -ForegroundColor White
    Write-Host "" 
    Write-Host "Would you like to continue with option 2? It will take longer but is more reliable." -ForegroundColor Yellow
    exit 1
}

# 4. Get ACR credentials
Write-Host "[4/7] Getting ACR credentials..." -ForegroundColor Cyan
$ACR_LOGIN_SERVER = az acr show --name $ACR_NAME --query loginServer --output tsv
$ACR_USERNAME = az acr credential show --name $ACR_NAME --query username --output tsv
$ACR_PASSWORD = az acr credential show --name $ACR_NAME --query passwords[0].value --output tsv

# 5. Create Container Apps environment
Write-Host "[5/7] Creating Container Apps environment..." -ForegroundColor Cyan
az containerapp env create `
  --name $CONTAINER_APP_ENV `
  --resource-group $RESOURCE_GROUP `
  --location $LOCATION

# 6. Deploy container app
Write-Host "[6/7] Deploying container app..." -ForegroundColor Cyan
az containerapp create `
  --name $CONTAINER_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --environment $CONTAINER_APP_ENV `
  --image "${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${TAG}" `
  --registry-server $ACR_LOGIN_SERVER `
  --registry-username $ACR_USERNAME `
  --registry-password $ACR_PASSWORD `
  --target-port 8000 `
  --ingress external `
  --cpu 1.0 `
  --memory 2.0Gi `
  --min-replicas 0 `
  --max-replicas 3 `
  --env-vars PORT=8000 SUMMARIZER_MODEL=sshleifer/distilbart-cnn-12-6

# 7. Get the app URL
Write-Host "[7/7] Getting application URL..." -ForegroundColor Cyan
$APP_URL = az containerapp show `
  --name $CONTAINER_APP_NAME `
  --resource-group $RESOURCE_GROUP `
  --query properties.configuration.ingress.fqdn `
  --output tsv

Write-Host ""
Write-Host "=== Deployment Complete ===" -ForegroundColor Green
Write-Host "Your API is available at: https://$APP_URL" -ForegroundColor Yellow
Write-Host "API Docs: https://$APP_URL/docs" -ForegroundColor Yellow
Write-Host "Health Check: https://$APP_URL/health" -ForegroundColor Yellow
Write-Host ""
Write-Host "To view logs:" -ForegroundColor Cyan
Write-Host "  az containerapp logs show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP --tail 50" -ForegroundColor White
