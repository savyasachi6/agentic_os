FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src

# Copy csproj and restore
COPY ["src/OpenClawToolsNode/OpenClawToolsNode.csproj", "OpenClawToolsNode/"]
RUN dotnet restore "OpenClawToolsNode/OpenClawToolsNode.csproj"

# Copy full source and build
COPY src/OpenClawToolsNode/ OpenClawToolsNode/
WORKDIR "/src/OpenClawToolsNode"
RUN dotnet build "OpenClawToolsNode.csproj" -c Release -o /app/build

FROM build AS publish
RUN dotnet publish "OpenClawToolsNode.csproj" -c Release -o /app/publish /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=publish /app/publish .
EXPOSE 8080
ENTRYPOINT ["dotnet", "OpenClawToolsNode.dll"]
