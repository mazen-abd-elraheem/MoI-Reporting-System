-- Add is_active field (REQUIRED for security)
ALTER TABLE dbo.[User]
ADD is_active BIT NOT NULL DEFAULT 1;

-- Add lastLoginAt field (OPTIONAL but recommended)
ALTER TABLE dbo.[User]
ADD lastLoginAt DATETIME NULL;

-- Add updatedAt field (OPTIONAL but recommended)
ALTER TABLE dbo.[User]
ADD updatedAt DATETIME NULL;

-- Add indexes for performance (RECOMMENDED)
CREATE INDEX IX_User_role ON dbo.[User](role);
CREATE INDEX IX_User_email ON dbo.[User](email);

-- OPTIONAL: Add tenant/client isolation (for multi-organization support)
-- Uncomment these if you want organization/department isolation:
/*
ALTER TABLE dbo.[User]
ADD tenant_id NVARCHAR(100) NULL;

ALTER TABLE dbo.[User]
ADD client_id NVARCHAR(100) NULL;

CREATE INDEX IX_User_tenant_id ON dbo.[User](tenant_id);
CREATE INDEX IX_User_client_id ON dbo.[User](client_id);
*/