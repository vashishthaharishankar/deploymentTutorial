<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ECR Docker Deployment Workflow</title>
</head>
<body>

  <h1>ECR Docker Deployment Workflow</h1>

  <p>This repository contains a GitHub Actions workflow (<code>ecr_docker_deployment.yml</code>) and a Dockerfile for deploying a Docker image to Amazon Elastic Container Registry (ECR) and updating an AWS Lambda function with the newly built image.</p>

  <h2>Workflow Description</h2>

  <h3>Workflow File (<code>ecr_docker_deployment.yml</code>)</h3>

  <p>The workflow is triggered on a <code>push</code> event to the repository. It consists of a single job <code>docker_cicd</code> which runs on an <code>ubuntu-latest</code> environment.</p>

  <h4>Steps:</h4>

  <ol>
    <li><strong>Checkout Repository:</strong> Checks out the repository code.</li>
    <li><strong>Configure AWS Credentials:</strong> Configures AWS credentials using <code>aws-actions/configure-aws-credentials@v1</code> GitHub Action. It requires AWS access key ID and secret access key stored as secrets in the repository.</li>
    <li><strong>Login to Amazon ECR:</strong> Uses <code>aws-actions/amazon-ecr-login@v2</code> to login to Amazon ECR using the configured AWS credentials.</li>
    <li><strong>Build, Tag, and Push Docker Image:</strong> Builds a Docker image using the Dockerfile provided in the repository, tags it, and pushes it to the specified Amazon ECR repository. It also updates an AWS Lambda function with the newly built image URI.</li>
  </ol>

  <h2>Dockerfile</h2>

  <p>The Dockerfile (<code>Dockerfile</code>) defines the environment and instructions for building the Docker image that will be deployed to Amazon ECR.</p>

  <h3>Description:</h3>

  <ul>
    <li><strong>Base Image:</strong> Uses <code>public.ecr.aws/lambda/python:3.12</code> as the base image, providing a Python 3.12 environment suitable for AWS Lambda functions.</li>
    <li><strong>Copying Requirements:</strong> Copies <code>requirements.txt</code> from the repository to the Lambda task root.</li>
    <li><strong>Installing Dependencies:</strong> Installs the Python dependencies specified in <code>requirements.txt</code> using <code>pip</code>.</li>
    <li><strong>Copying Function Code:</strong> Copies <code>lambda_function.py</code> from the repository to the Lambda task root.</li>
    <li><strong>Setting CMD:</strong> Sets the command to execute the Lambda function handler (<code>lambda_function.lambda_handler</code>).</li>
  </ul>

  <hr>

  <p>Feel free to modify and adapt the workflow and Dockerfile according to your project requirements! If you have any questions or need further assistance, please don't hesitate to reach out.</p>

</body>
</html>
