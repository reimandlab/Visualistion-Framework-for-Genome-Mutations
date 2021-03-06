import csv
import re
from warnings import warn

from database import db
from helpers.commands import got_permission


def add_column(engine, table_name, definition):
    sql = f'ALTER TABLE `{table_name}` ADD {definition}'
    engine.execute(sql)


def drop_column(engine, table_name, column_name):
    sql = f'ALTER TABLE `{table_name}` DROP `{column_name}`'
    engine.execute(sql)


def update_column(engine, table_name, column_definition):
    sql = f'ALTER TABLE `{table_name}` MODIFY COLUMN {column_definition}'
    engine.execute(sql)


def set_foreign_key_checks(engine, active=True):
    sql = f'SET FOREIGN_KEY_CHECKS={1 if active else 0};'
    if engine.dialect.name == 'sqlite':
        warn('Sqlite foreign key checks managements is not supported')
        return False
    engine.execute(sql)
    return True


def set_autocommit(engine, active=True):
    sql = f'SET AUTOCOMMIT={1 if active else 0};'
    if engine.dialect.name == 'sqlite':
        warn('Sqlite autocommit managements is not supported')
        return False
    engine.execute(sql)
    return True


def set_unique_checks(engine, active=True):
    sql = f'SET UNIQUE_CHECKS={1 if active else 0};'
    if engine.dialect.name == 'sqlite':
        warn('Sqlite unique key checks managements is not supported')
        return False
    engine.execute(sql)
    return True


def get_column_names(table):
    return set((i.name for i in table.c))


def mysql_extract_definitions(table_definition: str) -> dict:
    columns_definitions = {}

    to_replace = {
        r'TINYINT\(1\)': 'BOOL',  # synonymous for MySQL and SQLAlchemy
        r'INT\(11\)': 'INTEGER',
        'INT($| )': r'INTEGER\g<1>',
        'DOUBLE': 'FLOAT(53)',
        ' DEFAULT NULL': ''
    }

    for definition in table_definition.split('\n'):
        match = re.match(r'\s*`(?P<name>.*?)` (?P<definition>[^\n]*),\n?', definition)
        if match:
            name = match.group('name')
            definition_string = match.group('definition').upper()

            for mysql_explicit_definition, implicit_sqlalchemy in to_replace.items():
                definition_string = re.sub(
                    mysql_explicit_definition,
                    implicit_sqlalchemy,
                    definition_string
                )

            columns_definitions[name] = name + ' ' + definition_string

    return columns_definitions


def parse_csv(text: str) -> list:
    return list(csv.reader([text]))[0]


def mysql_columns_to_update(old_definitions: dict, new_definitions: dict) -> list:
    columns_to_update = []

    for column_name, new_definition in new_definitions.items():

        old_definition = old_definitions[column_name]
        differ = old_definition != new_definition

        enum_prefix = f'{column_name} ENUM('

        if differ and old_definition.startswith(enum_prefix) and new_definition.startswith(enum_prefix):
            old_values = set(parse_csv(old_definition[len(enum_prefix):-1].lower()))
            new_values = set(parse_csv(new_definition[len(enum_prefix):-1].lower()))
            differ = old_values != new_values

        if differ:
            columns_to_update.append([column_name, old_definition, new_definition])

    return columns_to_update


def basic_auto_migrate_relational_db(app, bind: str):
    """Inspired by http://stackoverflow.com/questions/2103274/"""

    from sqlalchemy import Table
    from sqlalchemy import MetaData

    print('Performing auto-migration in', bind, 'database...')
    db.session.commit()
    db.reflect(bind=bind)
    db.session.commit()
    db.create_all(bind=bind)

    with app.app_context():
        engine = db.get_engine(app, bind)
        tables = db.get_tables_for_bind(bind=bind)
        metadata = MetaData()
        metadata.engine = engine

        ddl = engine.dialect.ddl_compiler(engine.dialect, None)

        for table in tables:

            db_table = Table(
                table.name, metadata, autoload=True, autoload_with=engine
            )
            db_columns = get_column_names(db_table)

            columns = get_column_names(table)
            new_columns = columns - db_columns
            unused_columns = db_columns - columns
            existing_columns = columns.intersection(db_columns)

            for column_name in new_columns:
                column = getattr(table.c, column_name)
                if column.constraints:
                    print(f'Column {column_name} skipped due to existing constraints.')
                    continue
                print(f'Creating column: {column_name}')

                definition = ddl.get_column_specification(column)
                add_column(engine, table.name, definition)

            if engine.dialect.name == 'mysql':
                sql = f'SHOW CREATE TABLE `{table.name}`'
                table_definition = engine.execute(sql)
                new_definitions = {
                    column_name: ddl.get_column_specification(
                        getattr(table.c, column_name)
                    )
                    for column_name in existing_columns
                }
                old_definitions = mysql_extract_definitions(table_definition.first()[1])

                columns_to_update = mysql_columns_to_update(
                    old_definitions=old_definitions,
                    new_definitions=new_definitions
                )

                if columns_to_update:
                    print(
                        f'\nFollowing columns in `{table.name}` table differ in definitions '
                        f'from those specified in models: {columns_to_update}'
                    )
                for column, old_definition, new_definition in columns_to_update:
                    agreed = got_permission(
                        f'Column: `{column}`\n'
                        f'Old definition: {old_definition}\n'
                        f'New definition: {new_definition}\n'
                        'Update column definition?'
                    )
                    if agreed:
                        update_column(engine, table.name, new_definition)
                        print(f'Updated {column} column definition')
                    else:
                        print(f'Skipped {column} column')

            if unused_columns:
                print(
                    f'\nFollowing columns in `{table.name}` table are no longer used '
                    f'and can be safely removed: {unused_columns}'
                )
                for column in unused_columns:
                    if got_permission(f'Column: `{column}` - remove?'):
                        drop_column(engine, table.name, column)
                        print(f'Removed column {column}.')
                    else:
                        print(f'Keeping column {column}.')

    print('Auto-migration of', bind, 'database completed.')
