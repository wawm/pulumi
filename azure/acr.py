import * as pulumi from "@pulumi/pulumi";
import * as azure from "@pulumi/azure-native";

// 1. Create a Resource Group
const resourceGroup = new azure.resources.ResourceGroup("rg");

// 2. Create an Azure Key Vault
const keyVault = new azure.keyvault.Vault("kv", {
    resourceGroupName: resourceGroup.name,
    location: resourceGroup.location,
    properties: {
        tenantId: azure.config.tenantId!, // must be set
        sku: {
            family: "A",
            name: "standard",
        },
        accessPolicies: [], // We'll use RBAC, not access policies
        enableRbacAuthorization: true,
        publicNetworkAccess: "Enabled",
    },
});

// 3. Create a Key in the Key Vault
const key = new azure.keyvault.Key("cmk", {
    resourceGroupName: resourceGroup.name,
    vaultName: keyVault.name,
    keyName: "cmk-key",
    properties: {
        kty: "RSA",
        keySize: 2048,
        keyOps: ["wrapKey", "unwrapKey", "get"],
    },
});

// 4. Create a User-Assigned Managed Identity (UAMI)
const uami = new azure.managedidentity.UserAssignedIdentity("acr-uami", {
    resourceGroupName: resourceGroup.name,
    location: resourceGroup.location,
});

// 5. Grant the UAMI access to the Key Vault key ("wrapKey", "unwrapKey", "get")
const keyVaultKeyId = pulumi.interpolate`${keyVault.id}/keys/${key.name}`;
const roleAssignment = pulumi.all([uami.principalId, keyVaultKeyId]).apply(([principalId, keyId]) => {
    // The built-in role for Key Vault Crypto User
    // See: https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles#key-vault-crypto-service-encryption-user
    return new azure.authorization.RoleAssignment("uami-keyvault-key-access", {
        principalId: principalId!,
        principalType: "ServicePrincipal",
        roleDefinitionId: "/providers/Microsoft.Authorization/roleDefinitions/14b46e9e-c2b7-41b4-b07b-48a6ebf60603", // Key Vault Crypto Service Encryption User
        scope: keyId,
    });
});

// 6. Create the Azure Container Registry with encryption enabled using the CMK and UAMI
const acr = new azure.containerregistry.Registry("acr", {
    resourceGroupName: resourceGroup.name,
    location: resourceGroup.location,
    sku: {
        name: "Premium",
    },
    identity: {
        type: "UserAssigned",
        userAssignedIdentities: pulumi.output(uami.id).apply(id => ({ [id]: {} })),
    },
    encryption: {
        keyVaultProperties: {
            keyIdentifier: key.keyUri,
            identity: uami.clientId,
        },
    },
    adminUserEnabled: false,
});

// 7. Export the ACR login server and resource ID as stack outputs
export const acrLoginServer = acr.loginServer;
export const acrResourceId = acr.id;
