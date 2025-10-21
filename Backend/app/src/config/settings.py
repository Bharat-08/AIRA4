"""
Configuration management for the recruitment system.

This module handles all configuration loading, validation, and management
for the recruitment system, including environment variables, API keys,
and system settings.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class RecruitmentSettings(BaseModel):
    """Main configuration settings for the recruitment system."""
    
    # API Configuration
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", "your_openai_api_key_here"))
    pdl_api_key: str = Field(default_factory=lambda: os.getenv("PDL_API_KEY", "your_pdl_api_key_here"))
    
    # OpenAI Configuration
    openai_model: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o"))
    openai_temperature: float = Field(default_factory=lambda: float(os.getenv("OPENAI_TEMPERATURE", "0.1")))
    openai_max_tokens: int = Field(default_factory=lambda: int(os.getenv("OPENAI_MAX_TOKENS", "3000")))
    openai_timeout: int = Field(default_factory=lambda: int(os.getenv("OPENAI_TIMEOUT", "60")))
    
    # PDL Configuration
    pdl_base_url: str = Field(default_factory=lambda: os.getenv("PDL_BASE_URL", "https://api.peopledatalabs.com/v5/"))
    pdl_timeout: int = Field(default_factory=lambda: int(os.getenv("PDL_TIMEOUT", "60")))
    pdl_max_retries: int = Field(default_factory=lambda: int(os.getenv("PDL_MAX_RETRIES", "3")))
    
    # Search Configuration
    default_max_candidates: int = Field(default_factory=lambda: int(os.getenv("DEFAULT_MAX_CANDIDATES", "10")))
    max_search_queries: int = Field(default_factory=lambda: int(os.getenv("MAX_SEARCH_QUERIES", "5")))
    enable_elasticsearch_fallback: bool = Field(default_factory=lambda: os.getenv("ENABLE_ELASTICSEARCH_FALLBACK", "true").lower() == "true")
    
    # Output Configuration
    default_output_dir: str = Field(default_factory=lambda: os.getenv("DEFAULT_OUTPUT_DIR", "./results"))
    enable_csv_export: bool = Field(default_factory=lambda: os.getenv("ENABLE_CSV_EXPORT", "true").lower() == "true")
    enable_json_export: bool = Field(default_factory=lambda: os.getenv("ENABLE_JSON_EXPORT", "true").lower() == "true")
    
    # Logging Configuration
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_file: Optional[str] = Field(default_factory=lambda: os.getenv("LOG_FILE", "recruitment_system.log"))
    enable_file_logging: bool = Field(default_factory=lambda: os.getenv("ENABLE_FILE_LOGGING", "true").lower() == "true")
    enable_console_logging: bool = Field(default_factory=lambda: os.getenv("ENABLE_CONSOLE_LOGGING", "true").lower() == "true")
    
    # System Configuration
    workflow_version: str = Field(default_factory=lambda: os.getenv("WORKFLOW_VERSION", "2.0.0"))
    enable_caching: bool = Field(default_factory=lambda: os.getenv("ENABLE_CACHING", "false").lower() == "true")
    cache_ttl_seconds: int = Field(default_factory=lambda: int(os.getenv("CACHE_TTL_SECONDS", "3600")))
    
    # Performance Configuration
    concurrent_ranking_limit: int = Field(default_factory=lambda: int(os.getenv("CONCURRENT_RANKING_LIMIT", "5")))
    request_delay_seconds: float = Field(default_factory=lambda: float(os.getenv("REQUEST_DELAY_SECONDS", "0.1")))
    
    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of: {valid_levels}')
        return v.upper()
    
    @validator('default_output_dir')
    def validate_output_dir(cls, v):
        # Create directory if it doesn't exist
        Path(v).mkdir(parents=True, exist_ok=True)
        return v


class LoggingConfig:
    """Logging configuration and setup."""
    
    @staticmethod
    def setup_logging(settings: RecruitmentSettings) -> logging.Logger:
        """Set up logging configuration based on settings."""
        
        # Create logger
        logger = logging.getLogger('recruitment_system')
        logger.setLevel(getattr(logging, settings.log_level))
        
        # Clear existing handlers
        logger.handlers.clear()
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler
        if settings.enable_console_logging:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(getattr(logging, settings.log_level))
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        # File handler
        if settings.enable_file_logging and settings.log_file:
            try:
                file_handler = logging.FileHandler(settings.log_file, encoding='utf-8')
                file_handler.setLevel(getattr(logging, settings.log_level))
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            except Exception as e:
                logger.warning(f"Could not set up file logging: {e}")
        
        return logger


class ConfigurationManager:
    """Central configuration manager for the recruitment system."""
    
    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration manager."""
        self._settings = None
        self._logger = None
        self.config_file = config_file
        
    @property
    def settings(self) -> RecruitmentSettings:
        """Get or create settings instance."""
        if self._settings is None:
            try:
                self._settings = RecruitmentSettings()
            except Exception as e:
                raise ValueError(f"Failed to load configuration: {e}")
        return self._settings
    
    @property
    def logger(self) -> logging.Logger:
        """Get or create logger instance."""
        if self._logger is None:
            self._logger = LoggingConfig.setup_logging(self.settings)
        return self._logger
    
    def validate_configuration(self) -> Dict[str, Any]:
        """Validate the current configuration and return status."""
        validation_results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'api_keys': {},
            'directories': {},
            'settings': {}
        }
        
        try:
            settings = self.settings
            
            # Validate API keys
            if not settings.openai_api_key or settings.openai_api_key == "your_openai_api_key_here":
                validation_results['errors'].append("OpenAI API key is missing or invalid")
                validation_results['api_keys']['openai'] = False
            else:
                validation_results['api_keys']['openai'] = True
            
            if not settings.pdl_api_key or settings.pdl_api_key == "your_pdl_api_key_here":
                validation_results['errors'].append("PDL API key is missing or invalid")
                validation_results['api_keys']['pdl'] = False
            else:
                validation_results['api_keys']['pdl'] = True
            
            # Validate directories
            try:
                output_dir = Path(settings.default_output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                validation_results['directories']['output'] = True
            except Exception as e:
                validation_results['errors'].append(f"Cannot create output directory: {e}")
                validation_results['directories']['output'] = False
            
            # Check optional dependencies
            try:
                import PyPDF2
                validation_results['settings']['pdf_support'] = True
            except ImportError:
                validation_results['warnings'].append("PyPDF2 not installed - PDF support limited")
                validation_results['settings']['pdf_support'] = False
            
            # Set overall validity
            validation_results['valid'] = len(validation_results['errors']) == 0
            
        except Exception as e:
            validation_results['valid'] = False
            validation_results['errors'].append(f"Configuration validation failed: {e}")
        
        return validation_results
    
    def get_api_headers(self, service: str) -> Dict[str, str]:
        """Get API headers for a specific service."""
        settings = self.settings
        
        if service.lower() == 'openai':
            return {
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json"
            }
        elif service.lower() == 'pdl':
            return {
                "X-Api-Key": settings.pdl_api_key,
                "Content-Type": "application/json"
            }
        else:
            raise ValueError(f"Unknown service: {service}")
    
    def get_openai_config(self) -> Dict[str, Any]:
        """Get OpenAI-specific configuration."""
        settings = self.settings
        return {
            'model': settings.openai_model,
            'temperature': settings.openai_temperature,
            'max_tokens': settings.openai_max_tokens,
            'timeout': settings.openai_timeout
        }
    
    def get_pdl_config(self) -> Dict[str, Any]:
        """Get PDL-specific configuration."""
        settings = self.settings
        return {
            'base_url': settings.pdl_base_url,
            'timeout': settings.pdl_timeout,
            'max_retries': settings.pdl_max_retries
        }
    
    def update_setting(self, key: str, value: Any) -> None:
        """Update a specific setting (for runtime configuration)."""
        if hasattr(self.settings, key):
            setattr(self.settings, key, value)
            self.logger.info(f"Updated setting {key} = {value}")
        else:
            raise ValueError(f"Unknown setting: {key}")
    
    def export_config(self) -> Dict[str, Any]:
        """Export current configuration (excluding sensitive data)."""
        settings = self.settings
        config_dict = settings.dict()
        
        # Mask sensitive information
        sensitive_keys = ['openai_api_key', 'pdl_api_key']
        for key in sensitive_keys:
            if key in config_dict and config_dict[key]:
                config_dict[key] = f"***{config_dict[key][-4:]}" if len(config_dict[key]) > 4 else "***"
        
        return config_dict


# Global configuration instance
config_manager = ConfigurationManager()

# Convenience functions for easy access
def get_settings() -> RecruitmentSettings:
    """Get the global settings instance."""
    return config_manager.settings

def get_logger() -> logging.Logger:
    """Get the global logger instance."""
    return config_manager.logger

def validate_config() -> Dict[str, Any]:
    """Validate the global configuration."""
    return config_manager.validate_configuration()


gemini_api_key: str = Field(default='')
gemini_model: str = Field(default='gemini-2.5-pro')  # CORRECTED
discovery_enabled: bool = Field(default=False)
discovery_max_iterations: int = Field(default=5)
discovery_candidates_per_seed: int = Field(default=5)
discovery_top_seeds: int = Field(default=3)

# Export main components
__all__ = [
    'RecruitmentSettings',
    'LoggingConfig', 
    'ConfigurationManager',
    'config_manager',
    'get_settings',
    'get_logger',
    'validate_config'
]