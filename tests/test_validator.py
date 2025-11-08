import pytest
from src.llm.validator import SQLValidator

def test_validator_accepts_safe_select():
    validator = SQLValidator(allowed_table="dev_diamond2")
    
    sql = "SELECT * FROM public.dev_diamond2 LIMIT 10;"
    is_valid, error = validator.validate(sql)
    
    assert is_valid is True
    assert error is None

def test_validator_rejects_insert():
    validator = SQLValidator(allowed_table="dev_diamond2")
    
    sql = "INSERT INTO dev_diamond2 (col) VALUES (1);"
    is_valid, error = validator.validate(sql)
    
    assert is_valid is False
    assert "INSERT" in error

def test_validator_rejects_delete():
    validator = SQLValidator(allowed_table="dev_diamond2")
    
    sql = "DELETE FROM dev_diamond2 WHERE id=1;"
    is_valid, error = validator.validate(sql)
    
    assert is_valid is False
    assert "DELETE" in error

def test_validator_rejects_drop():
    validator = SQLValidator(allowed_table="dev_diamond2")
    
    sql = "DROP TABLE dev_diamond2;"
    is_valid, error = validator.validate(sql)
    
    assert is_valid is False
    assert "DROP" in error

def test_validator_rejects_multiple_statements():
    validator = SQLValidator(allowed_table="dev_diamond2")
    
    sql = "SELECT * FROM dev_diamond2; SELECT * FROM users;"
    is_valid, error = validator.validate(sql)
    
    assert is_valid is False
    assert "Multiple" in error

def test_validator_rejects_wrong_table():
    validator = SQLValidator(allowed_table="dev_diamond2")
    
    sql = "SELECT * FROM other_table LIMIT 10;"
    is_valid, error = validator.validate(sql)
    
    assert is_valid is False
    assert "dev_diamond2" in error

def test_validator_enforces_limit():
    validator = SQLValidator(allowed_table="dev_diamond2")
    
    sql = "SELECT * FROM dev_diamond2"
    fixed_sql = validator.enforce_limit(sql)
    
    assert "LIMIT" in fixed_sql.upper()

def test_validator_replaces_high_limit():
    validator = SQLValidator(allowed_table="dev_diamond2")
    
    sql = "SELECT * FROM dev_diamond2 LIMIT 10"
    fixed_sql = validator.enforce_limit(sql, limit=5)
    
    assert "LIMIT 5" in fixed_sql
