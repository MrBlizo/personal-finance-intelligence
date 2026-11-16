import 'dart:io';

import 'package:pfi/data/db.dart';
import 'package:pfi/data/schema.dart';

final schemaSql = File('assets/db/schema.sql').readAsStringSync();
final schemaMeta = SchemaMeta.parse(File('assets/db/schema.json').readAsStringSync());

AppDatabase memoryDb() => AppDatabase.open(':memory:', schemaSql, schemaMeta);
