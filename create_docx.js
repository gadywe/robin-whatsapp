const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, 
        HeadingLevel, AlignmentType, WidthType, BorderStyle, ShadingType } = require('docx');
const fs = require('fs');
const sqlite3 = require('sqlite3').verbose();

const db = new sqlite3.Database('robin.db');

db.all("SELECT chat_id, role, content, timestamp FROM messages ORDER BY timestamp ASC", 
  (err, rows) => {
    if (err) {
      console.error(err);
      process.exit(1);
    }

    const border = { style: BorderStyle.SINGLE, size: 6, color: "CCCCCC" };
    const borders = { top: border, bottom: border, left: border, right: border };

    // Table rows
    const tableRows = [
      // Header row
      new TableRow({
        children: [
          new TableCell({
            borders,
            shading: { fill: "4472C4", type: ShadingType.CLEAR },
            children: [new Paragraph({
              children: [new TextRun({ text: "Time", bold: true, color: "FFFFFF", size: 22 })]
            })]
          }),
          new TableCell({
            borders,
            shading: { fill: "4472C4", type: ShadingType.CLEAR },
            children: [new Paragraph({
              children: [new TextRun({ text: "Sender", bold: true, color: "FFFFFF", size: 22 })]
            })]
          }),
          new TableCell({
            borders,
            shading: { fill: "4472C4", type: ShadingType.CLEAR },
            children: [new Paragraph({
              children: [new TextRun({ text: "Message", bold: true, color: "FFFFFF", size: 22 })]
            })]
          })
        ]
      })
    ];

    // Data rows
    rows.forEach((row, idx) => {
      const date = new Date(row.timestamp * 1000).toLocaleString('en-IL');
      const sender = row.role === 'user' ? 'GADI' : 'ROBIN';
      const msgPreview = row.content.substring(0, 200);

      tableRows.push(
        new TableRow({
          children: [
            new TableCell({
              borders,
              shading: { fill: idx % 2 === 0 ? "F0F0F0" : "FFFFFF", type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: date, size: 20 })] })]
            }),
            new TableCell({
              borders,
              shading: { fill: idx % 2 === 0 ? "F0F0F0" : "FFFFFF", type: ShadingType.CLEAR },
              children: [new Paragraph({
                children: [new TextRun({
                  text: sender,
                  bold: sender === 'ROBIN',
                  color: sender === 'ROBIN' ? '0070C0' : '000000',
                  size: 20
                })]
              })]
            }),
            new TableCell({
              borders,
              shading: { fill: idx % 2 === 0 ? "F0F0F0" : "FFFFFF", type: ShadingType.CLEAR },
              children: [new Paragraph({ children: [new TextRun({ text: msgPreview, size: 20 })] })]
            })
          ]
        })
      );
    });

    const doc = new Document({
      sections: [{
        properties: {
          page: {
            size: { width: 12240, height: 15840 },
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
          }
        },
        children: [
          new Paragraph({
            heading: HeadingLevel.HEADING_1,
            children: [new TextRun({ text: "Robin Conversation Transcript", bold: true, size: 32 })]
          }),
          new Paragraph({ children: [new TextRun("")] }),
          new Table({
            width: { size: 9360, type: WidthType.DXA },
            columnWidths: [2000, 1500, 5860],
            rows: tableRows
          }),
          new Paragraph({ children: [new TextRun("")] }),
          new Paragraph({
            heading: HeadingLevel.HEADING_2,
            children: [new TextRun({ text: `Summary: ${rows.length} total messages`, bold: true, size: 26 })]
          })
        ]
      }]
    });

    Packer.toBuffer(doc).then(buffer => {
      fs.writeFileSync("robin_conversation.docx", buffer);
      console.log("Created: robin_conversation.docx");
      process.exit(0);
    });
  }
);
