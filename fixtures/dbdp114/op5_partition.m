let
  Source = Csv.Document(File.Contents("C:\\Users\\peter\\OneDrive\\Documents\\Gemini\\PB27_Defense_Wide_OM_Executive_Dashboard\\data\\Defense_Wide_OM_PB27.csv"),[Delimiter=",", Columns=28, Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
  #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
  #"Replaced Nulls" = Table.ReplaceValue(#"Promoted Headers",null,"Core Operations",Replacer.ReplaceValue,{"budget_activity_title"}),
  #"Replaced Blanks" = Table.ReplaceValue(#"Replaced Nulls","","Core Operations",Replacer.ReplaceValue,{"budget_activity_title"}),
  #"Renamed Columns" = Table.RenameColumns(#"Replaced Blanks",{{"Attribute", "FY"}, {"Sum of Value", "Amount"}}),
  #"Changed Type" = Table.TransformColumnTypes(#"Renamed Columns",{{"FY", Int64.Type}, {"Amount", type number}})
in
  #"Changed Type"
