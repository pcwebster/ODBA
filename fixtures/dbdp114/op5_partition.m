// OP5 import query (Power Query M).
// FixtureRoot is a Power Query text parameter: the full path of the folder that
// holds Defense_Wide_OM_PB27.csv, ending in a path separator. In a clone of this
// repo that folder is fixtures/dbdp114/. To set it in Power BI Desktop: Transform
// data > Manage Parameters > New Parameter, name FixtureRoot, type Text, and enter
// your local path, for example <your clone>\fixtures\dbdp114\
// In TMDL the parameter is an expression:
//   expression FixtureRoot = "<your clone>\fixtures\dbdp114\" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]
let
  Source = Csv.Document(File.Contents(FixtureRoot & "Defense_Wide_OM_PB27.csv"),[Delimiter=",", Columns=28, Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
  #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
  #"Replaced Nulls" = Table.ReplaceValue(#"Promoted Headers",null,"Core Operations",Replacer.ReplaceValue,{"budget_activity_title"}),
  #"Replaced Blanks" = Table.ReplaceValue(#"Replaced Nulls","","Core Operations",Replacer.ReplaceValue,{"budget_activity_title"}),
  #"Renamed Columns" = Table.RenameColumns(#"Replaced Blanks",{{"Attribute", "FY"}, {"Sum of Value", "Amount"}}),
  #"Changed Type" = Table.TransformColumnTypes(#"Renamed Columns",{{"FY", Int64.Type}, {"Amount", type number}})
in
  #"Changed Type"
